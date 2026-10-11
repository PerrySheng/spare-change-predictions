import test from 'node:test';
import assert from 'node:assert/strict';
import {GoogleEventReader, googleModelCall} from './google.js';

test('only public note strings from real output are streamed; thoughts are discarded',()=>{
 const packets:any[]=[];
 const reader=new GoogleEventReader('News Scout',p=>packets.push(p));
 reader.event({candidates:[{content:{parts:[{thought:true,text:'private reasoning',thoughtSignature:'secret'}]}}]} as any);
 reader.event({candidates:[{content:{parts:[{text:'{"public_notes":["Found public evidence",'}]}}]} as any);
 reader.event({candidates:[{content:{parts:[{text:'"Sources remain limited"],"probability":0.5}'}]},finishReason:'STOP'}]} as any);
 assert.deepEqual(packets.map(p=>p.data.text),['Found public evidence\n','Sources remain limited\n']);
 assert.equal(reader.text,'{"public_notes":["Found public evidence","Sources remain limited"],"probability":0.5}');
 assert.equal(reader.finishReason,'STOP');
 assert.ok(!JSON.stringify(packets).includes('private reasoning'));
});

test('Google call uses streamed JSON, no paid search tool, and measured usage',async()=>{
 let request:any; const packets:any[]=[];
 const client:any={models:{generateContentStream:async(params:any)=>{
  request=params;
  return (async function*(){yield {candidates:[{content:{parts:[{text:'{"public_notes":["Public fact"],"probability":0.5}'}]},finishReason:'STOP'}],usageMetadata:{promptTokenCount:12,candidatesTokenCount:7,thoughtsTokenCount:3,cachedContentTokenCount:2}};})();
 }}};
 const usage={input_tokens:0,output_tokens:0,cache_creation_input_tokens:0,cache_read_input_tokens:0,web_search_requests:0,model_calls:1};
 const answer=await googleModelCall(client,'configured-model','News Scout','Prompt',p=>packets.push(p),usage);
 assert.equal(answer.json.probability,0.5);
 assert.equal(request.config.responseMimeType,'application/json');
 assert.equal(request.config.tools,undefined);
 assert.equal(request.config.thinkingConfig.includeThoughts,false);
 assert.deepEqual(request.config.responseJsonSchema.properties.probability,{type:'number',minimum:0,maximum:1});
 assert.equal(usage.input_tokens,12);assert.equal(usage.output_tokens,10);assert.equal(usage.cache_read_input_tokens,2);
 assert.equal(usage.web_search_requests,0);
});

test('blocked or truncated Google output never becomes a forecast',async()=>{
 const client:any={models:{generateContentStream:async()=> (async function*(){yield {candidates:[{content:{parts:[{text:'{"probability":0.5}'}]},finishReason:'MAX_TOKENS'}]};})()}};
 const usage={input_tokens:0,output_tokens:0,cache_creation_input_tokens:0,cache_read_input_tokens:0,web_search_requests:0,model_calls:1};
 await assert.rejects(googleModelCall(client,'model','Skeptic','Prompt',()=>{},usage),/incomplete/);
});
