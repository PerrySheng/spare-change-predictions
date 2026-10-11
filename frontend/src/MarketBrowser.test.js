import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
import {demoMarketEvents} from './demoMarkets.js';

// Node rendering checks semantics and quotes, without launching a browser.
test('event picker renders accessible binary, full-event and isolated demo actions',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false},appType:'custom'});
 try{
  const {default:MarketBrowser,MarketEventCard}=await server.ssrLoadModule('/src/MarketBrowser.jsx');
  const props={user:{id:'profile'},onBet:()=>{},onResearch:()=>{},onSwarm:()=>{}};
  const real={id:'E',title:'Will it rain?',category:'Weather',source:'gemini',outcomes:[{id:'C',title:'Will it rain?',label:'Rain',event_ticker:'E',prices:{yes:'.3',no:'.85'}}]};
  const html=renderToStaticMarkup(React.createElement(MarketBrowser,{...props,suggestions:{events:[real],markets:[]}}));
  assert.match(html,/Search markets/);
  assert.match(html,/Demo examples/);
  assert.match(html,/30¢/);
  assert.match(html,/85¢/);
  assert.match(html,/30%/);
  assert.match(html,/aria-pressed="false"/);
  assert.match(html,/Read in News/);
  const loading=renderToStaticMarkup(React.createElement(MarketBrowser,{...props,suggestions:null,loading:true}));
  assert.match(loading,/Finding markets that fit your change/);
  assert.doesNotMatch(loading,/No tailored markets available/);
  const demo=renderToStaticMarkup(React.createElement(MarketEventCard,{...props,event:demoMarketEvents[1],selected:'demo-basketball-celtics:yes'}));
  assert.match(demo,/Demo/);
  assert.match(demo,/aria-expanded="false"/);
  assert.match(demo,/Show 2 more outcomes/);
  assert.doesNotMatch(demo,/Read in News|Swarm research/);
  assert.ok(demo.indexOf('Boston Celtics')<demo.indexOf('Denver Nuggets'));
  assert.doesNotMatch(demo,/Milwaukee Bucks/);
  assert.match(demo,/aria-pressed="true"/);
  const missing=renderToStaticMarkup(React.createElement(MarketEventCard,{...props,event:{...real,outcomes:[{...real.outcomes[0],prices:{yes:null,no:'.85'}}]}}));
  assert.match(missing,/Quote unavailable/);
  assert.match(missing,/disabled=""/);
  assert.doesNotMatch(missing,/15%|15¢/);
 }finally{await server.close()}
});
