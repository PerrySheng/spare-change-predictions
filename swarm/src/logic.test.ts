import assert from "node:assert/strict";
import test from "node:test";
import type {RawMessageStreamEvent} from "@anthropic-ai/sdk/resources/messages";
import {AGENTS, allowSearch, median, validateEstimate, type Packet} from "./logic.js";
import {ProviderEventReader} from "./worker.js";

test("median uses all four revisions and does not trust a synthesizer number", () => {
  assert.equal(median([.8, .2, .6, .4]), .5);
  assert.throws(() => median([.2, .4, .6]));
  assert.throws(() => median([.2, .4, .6, Number.NaN]));
});

test("market reader and debate never receive a web search tool", () => {
  for (const agent of AGENTS) {
    assert.equal(allowSearch(agent, 2, []), false);
    assert.equal(allowSearch(agent, 1, [{url:"https://evidence.example/",title:"Existing evidence"}]), false);
  }
  assert.equal(allowSearch("Market Reader", 1, []), false);
  assert.equal(allowSearch("News Scout", 1, []), true);
});

test("unknown citations and incomplete revision output are rejected", () => {
  const estimate = {probability:.4, confidence:"low", reasons:["a","b","c"], sources:["https://evidence.example/"]};
  assert.throws(() => validateEstimate(estimate, new Set()));
  assert.throws(() => validateEstimate(estimate, new Set(estimate.sources), true));
  assert.equal(validateEstimate({...estimate,revision_reason:"A documented change"},new Set(estimate.sources),true).probability,.4);
});

test("search queries are parsed from actual complete input JSON, not initial empty inputs", () => {
  const events: Packet[] = [];
  const reader = new ProviderEventReader("News Scout", e => events.push(e), () => {});
  const raw = (value: unknown) => reader.event(value as RawMessageStreamEvent);
  raw({type:"content_block_start",index:1,content_block:{type:"server_tool_use",id:"s",name:"web_search",input:{}}});
  raw({type:"content_block_delta",index:1,delta:{type:"input_json_delta",partial_json:'{"query":"actual'}});
  assert.equal(events.length,0);
  raw({type:"content_block_delta",index:1,delta:{type:"input_json_delta",partial_json:' public query"}'}});
  raw({type:"content_block_stop",index:1});
  assert.deepEqual(events,[{type:"search_query",data:{agent:"News Scout",query:"actual public query"}}]);
});

test("thinking and final JSON are withheld; public visible evidence and sources remain", () => {
  const events: Packet[] = [];
  const sources: Record<string, unknown>[] = [];
  const reader = new ProviderEventReader("Skeptic", e=>events.push(e), (_agent,row)=>sources.push(row));
  const raw = (value: unknown) => reader.event(value as RawMessageStreamEvent);
  raw({type:"content_block_start",index:0,content_block:{type:"thinking",thinking:"",signature:""}});
  raw({type:"content_block_delta",index:0,delta:{type:"thinking_delta",thinking:"private hidden reasoning"}});
  raw({type:"content_block_start",index:1,content_block:{type:"text",text:""}});
  raw({type:"content_block_delta",index:1,delta:{type:"text_delta",text:"A public evidence observation."}});
  raw({type:"content_block_start",index:2,content_block:{type:"text",text:""}});
  raw({type:"content_block_delta",index:2,delta:{type:"text_delta",text:'{"probability":.4}'}});
  raw({type:"content_block_start",index:3,content_block:{type:"web_search_tool_result",tool_use_id:"s",content:[{type:"web_search_result",url:"https://evidence.example/",title:"An observed source",encrypted_content:"opaque private content"}]}});
  assert.deepEqual(events,[{type:"evidence_note",data:{agent:"Skeptic",text:"A public evidence observation."}}]);
  assert.deepEqual(sources,[{url:"https://evidence.example/",title:"An observed source"}]);
  assert.ok(!JSON.stringify({events,sources}).includes("private"));
});
