import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
test('occupied markets and researched legs keep the human owner and funding visible',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false},appType:'custom'});
 try{
  const {marketTakenBy,LegCard}=await server.ssrLoadModule('/src/GroupTab.jsx');
  const leg={id:'l',market_id:'m',user_id:'a',user_name:'Alex',category:'weather',title:'Will it rain?',outcome:'no',entry_price:'.8',status:'open',votes:[],agree_count:0,disagree_count:0,swarm_research:{run_id:'r'}};
  assert.equal(marketTakenBy([leg],'b','m'),leg);
  assert.equal(marketTakenBy([leg],'a','m'),null);
  assert.equal(marketTakenBy([leg],'b','other'),null);
  const html=renderToStaticMarkup(React.createElement(LegCard,{leg,user:{id:'a'},onSwarm:()=>{},onAsk:()=>{}}));
  assert.match(html,/Alex · you/);assert.match(html,/Swarm researched/);assert.match(html,/Swarm contributes no money/);
  const {default:Picker}=await server.ssrLoadModule('/src/SwarmLegPicker.jsx');
  const action=renderToStaticMarkup(React.createElement(Picker,{user:{id:'a'},run:{id:'r',market_id:'m',outcome:'yes'}}));
  assert.match(action,/Use as my squad leg/);assert.match(action,/You choose the side and fund your own leg/);
 }finally{await server.close()}
});

test('squad picker hides a friends entire reserved event and puts distinct events first',async()=>{
 const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false},appType:'custom'});
 try{
  const {availableSquadMarkets}=await server.ssrLoadModule('/src/GroupTab.jsx');
  assert.equal(typeof availableSquadMarkets,'function');
  const markets=[{id:'taken',event_ticker:'GAME'},{id:'other-team',event_ticker:'GAME'},{id:'own',event_ticker:'OWN'},{id:'own-other',event_ticker:'OWN'},{id:'rain',event_ticker:'WEATHER'}];
  const legs=[{user_id:'a',market_id:'taken',event_ticker:'GAME'},{user_id:'b',market_id:'own',event_ticker:'OWN'}];
  assert.deepEqual(availableSquadMarkets(markets,legs,'b').map(m=>m.id),['own','rain','own-other']);
  const cutoff=2000000000;
  const dates=[{id:'early',event_ticker:'EARLY',closes_at:new Date((cutoff+946684800-86400-1)*1000).toISOString()},{id:'late',event_ticker:'LATE',closes_at:new Date((cutoff+946684800)*1000).toISOString()}];
  assert.deepEqual(availableSquadMarkets(dates,[],'b',cutoff).map(m=>m.id),['early']);
 }finally{await server.close()}
});
