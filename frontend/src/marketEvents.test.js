import test from 'node:test';
import assert from 'node:assert/strict';
import {groupSuggestedEvents,filterMarketEvents,orderMarketOutcomes,selectMarketEvents,marketProbability,sideChoice} from './marketEvents.js';
import {demoMarketEvents} from './demoMarkets.js';

const suggestions={markets:[
 {id:'river-a',event_ticker:'RIVER',title:'Who will win the race?',label:'Ava',category:'Politics',topic:'politics',why:'Matches your interests.',outcomes:[{outcome:'yes',price:'.2',selectable:true,quote:{quantity:2,total_cents:43}},{outcome:'no',price:'.83',selectable:false,reason:'unaffordable'}]},
 {id:'river-b',event_ticker:'RIVER',title:'Who will win the race?',label:'Ben',category:'Politics',topic:'politics',outcomes:[{outcome:'yes',price:'.6',selectable:true},{outcome:'no',price:null,selectable:false}]},
 {id:'rain',event_ticker:'RAIN',title:'Will it rain?',label:'Rain',category:'Weather',topic:'weather',outcomes:[{outcome:'yes',price:'.7',selectable:true},{outcome:'no',price:'.35',selectable:true}]},
]};

test('tailored contracts group by event without dropping contract identity or independent side quotes',()=>{
 const events=groupSuggestedEvents(suggestions);
 assert.equal(events.length,2);
 assert.deepEqual(events[0].outcomes.map(m=>m.id),['river-a','river-b']);
 assert.deepEqual(events[0].outcomes[0].prices,{yes:'.2',no:'.83'});
 assert.equal(events[0].outcomes[0].event_ticker,'RIVER');
 assert.equal(events[0].outcomes[0].why,'Matches your interests.');
 assert.equal(sideChoice(events[0].outcomes[0],'yes').quote.total_cents,43);
 assert.equal(sideChoice(events[0].outcomes[0],'no').available,false);
 assert.equal(sideChoice(events[0].outcomes[1],'no').available,false);
});

test('duplicate suggested sides combine instead of replacing an existing observed quote',()=>{
 const rows={markets:[{id:'one',event_ticker:'E',title:'Question',outcome:'yes',price:'.25'},{id:'one',event_ticker:'E',title:'Question',outcome:'no',price:'.8'}]};
 const events=groupSuggestedEvents(rows);
 assert.equal(events[0].outcomes.length,1);
 assert.deepEqual(events[0].outcomes[0].prices,{yes:'.25',no:'.8'});
});

test('search matches event context and outcome labels, retaining every sibling outcome',()=>{
 const events=groupSuggestedEvents(suggestions);
 assert.equal(filterMarketEvents(events,' POLITICS ')[0].outcomes.length,2);
 assert.equal(filterMarketEvents(events,'Ava')[0].outcomes.length,2);
 assert.deepEqual(filterMarketEvents(events,'does not exist'),[]);
 assert.equal(filterMarketEvents(events,'').length,2);
});

test('probabilities sort descending with unquoted contracts last without mutating the event',()=>{
 const outcomes=[{id:'missing',prices:{yes:null,no:'.4'}},{id:'low',prices:{yes:'.1',no:'.95'}},{id:'high',prices:{yes:'.6',no:'.47'}},{id:'explicit',implied_probability:.8,prices:{yes:'.65',no:'.4'}}];
 assert.deepEqual(orderMarketOutcomes(outcomes).map(m=>m.id),['explicit','high','low','missing']);
 assert.equal(outcomes[0].id,'missing');
 assert.equal(marketProbability(outcomes[0]),null);
 assert.equal(marketProbability(outcomes[3]),.8);
});

test('empty real search shows tailored events and nonempty search uses only the catalog',()=>{
 const catalog=[{id:'CATALOG',title:'A different race',category:'Sports',outcomes:[{id:'catalog-contract',label:'Ava'}]}];
 assert.deepEqual(selectMarketEvents({suggestions,catalog,query:''}),groupSuggestedEvents(suggestions));
 assert.deepEqual(selectMarketEvents({suggestions,catalog,query:'Ava'}),catalog);
 assert.deepEqual(selectMarketEvents({suggestions,catalog:null,query:'Ava'}),[]);
});

test('tailored full-event payload retains all sibling contracts and carries the recommended explanation',()=>{
 const full={...suggestions,events:[{id:'RIVER',title:'Who will win the race?',category:'Politics',topic:'politics',source:'gemini',outcomes:[
  {id:'river-a',label:'Ava',prices:{yes:'.2',no:'.83'}},
  {id:'river-b',label:'Ben',prices:{yes:'.6',no:null}},
  {id:'river-c',label:'Casey',prices:{yes:'.1',no:'.94'}},
 ]}]};
 const events=selectMarketEvents({suggestions:full,query:''});
 assert.equal(events.length,1);
 assert.equal(events[0].outcomes.length,3);
 assert.equal(events[0].why,'Matches your interests.');
 assert.equal(events[0].outcomes[2].title,'Who will win the race?');
 assert.equal(events[0].outcomes[2].event_ticker,'RIVER');
 assert.deepEqual(events[0].outcomes[2].prices,{yes:'.1',no:'.94'});
 assert.equal(sideChoice(events[0].outcomes[0],'no').available,false);
});

test('demo examples stay explicitly isolated from both tailored and catalog sources',()=>{
 const events=selectMarketEvents({suggestions,catalog:[{id:'LIVE',title:'Bitcoin',outcomes:[]}],demo:true,query:''});
 assert.equal(events.length,demoMarketEvents.length);
 assert.ok(events.some(e=>e.outcomes.length===1));
 assert.ok(events.some(e=>e.outcomes.length>4));
 assert.ok(events.every(e=>e.source==='demo'&&e.outcomes.every(m=>m.source==='demo'&&m.id.startsWith('demo-'))));
 const searched=selectMarketEvents({suggestions,catalog:[],demo:true,query:'Bitcoin'});
 assert.equal(searched[0].id,'demo-bitcoin');
 assert.equal(searched[0].source,'demo');
});

test('unavailable, invalid and unaffordable sides never become executable through display adapters',()=>{
 for(const price of [null,undefined,'',0,1,-.1,'bad',Infinity]){
  assert.equal(sideChoice({prices:{yes:price,no:'.2'}},'yes').available,false);
 }
 assert.equal(sideChoice({prices:{yes:'.3',no:'.85'}},'no').price,'.85');
 assert.equal(sideChoice({prices:{yes:null,no:'.85'}},'yes').available,false);
 assert.equal(marketProbability({prices:{yes:null,no:'.85'}}),null);
});
