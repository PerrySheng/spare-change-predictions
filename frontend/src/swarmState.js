export const roles=['News Scout','Base Rate Analyst','Market Reader','Skeptic'];
export const names=Object.fromEntries([...roles,'Synthesizer'].map(n=>[n,n]));
export function addEvent(events,event){if(!event||!Number.isInteger(event.id)||!event.type)return events;return [...events.filter(e=>e.id!==event.id),event].sort((a,b)=>a.id-b.id)}
export function agentState(events,agent){
 let state={state:'waiting',round:1,previous_estimate:null,notes:'',queries:[],sources:[],estimate:null,revision:null};
 for(const event of events){const d=event.data||{};if(d.agent!==agent)continue;
  if(event.type==='agent_started')state={...state,state:d.round===2?'debating':agent==='Market Reader'?'reading':'thinking',round:d.round||1};
  if(event.type==='search_query')state={...state,state:'searching',queries:[...state.queries,d.query]};
  if(event.type==='source_found')state={...state,state:'reading',sources:[...state.sources.filter(s=>s.url!==d.url),d]};
  if(event.type==='evidence_note')state={...state,state:state.round===2?'debating':'thinking',notes:(state.notes+(d.text||'')).slice(-40000)};
  if(['estimate_submitted','estimate_revised','agent_revised'].includes(event.type))state={...state,state:'done',previous_estimate:d.round===2?state.estimate:state.previous_estimate,estimate:d.probability,revision:d.revision_reason||null};
 }
 return state;
}
export function safeSource(url){try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null}catch{return null}}
