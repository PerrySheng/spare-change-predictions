import {test} from 'node:test';
import assert from 'node:assert/strict';
import {addEvent,agentState,safeSource} from './swarmState.js';
test('agent states come only from actual events; replay preserves ordering',()=>{
 let events=[];events=addEvent(events,{id:2,type:'search_query',data:{agent:'News Scout',query:'report'}});
 events=addEvent(events,{id:1,type:'agent_started',data:{agent:'News Scout',round:1}});
 events=addEvent(events,{id:2,type:'search_query',data:{agent:'News Scout',query:'report'}});
 assert.equal(events.length,2);assert.equal(agentState(events,'News Scout').state,'searching');
 assert.equal(agentState(events,'Skeptic').state,'waiting');
 events=addEvent(events,{id:3,type:'estimate_submitted',data:{agent:'News Scout',probability:0.3}});
 events=addEvent(events,{id:4,type:'agent_started',data:{agent:'News Scout',round:2}});
 assert.equal(agentState(events,'News Scout').state,'debating');assert.equal(agentState(events,'News Scout').estimate,0.3);
 events=addEvent(events,{id:5,type:'estimate_revised',data:{agent:'News Scout',round:2,probability:0.5,revision_reason:'Updated evidence'}});
 assert.equal(agentState(events,'News Scout').previous_estimate,0.3);assert.equal(agentState(events,'News Scout').estimate,0.5);
 assert.equal(agentState(events.slice(0,1),'News Scout').state,'thinking');
});
test('source links refuse executable or credential-bearing URLs',()=>{assert.equal(safeSource('javascript:alert(1)'),null);assert.equal(safeSource('https://a:b@example.com'),null);assert.equal(safeSource('https://example.com/story'),'https://example.com/story')});
test('a cached chip never reuses a forecast after a user, market, or side swap',async()=>{
 const {matchingForecast}=await import('./swarmState.js');
 const run={id:'run',status:'completed',user_id:'alice',market_id:'market-one',outcome:'yes',result:{probability:.6}};
 assert.equal(matchingForecast(run,'alice','market-one','yes'),run);
 assert.equal(matchingForecast(run,'bob','market-one','yes'),null);
 assert.equal(matchingForecast(run,'alice','market-two','yes'),null);
 assert.equal(matchingForecast(run,'alice','market-one','no'),null);
 assert.equal(matchingForecast({...run,status:'running'},'alice','market-one','yes'),null);
});
