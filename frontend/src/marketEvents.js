import {demoMarketEvents} from './demoMarkets.js';

const sides=['yes','no'];
function numericProbability(value){
 if(value==null||value==='')return null;
 const number=Number(value);
 return Number.isFinite(number)&&number>=0&&number<=1?number:null;
}

export function marketProbability(market){
 return numericProbability(market.implied_probability)??numericProbability(market.prices?.yes);
}

export function sideChoice(market,side){
 const choice=(market.outcomes||[]).find(o=>o.outcome===side);
 const price=choice?.price??market.prices?.[side]??null;
 const numeric=numericProbability(price);
 return {...choice,price,available:numeric!=null&&numeric>0&&numeric<1&&choice?.selectable!==false};
}

/** Preserve observed YES and NO quotes independently; a missing side stays null. */
export function groupSuggestedEvents(suggestions){
 const events=new Map();
 for(const market of suggestions?.markets||[]){
  if(!market.id)continue;
  const id=market.event_ticker||market.id;
  if(!events.has(id))events.set(id,{id,title:market.title,category:market.category,topic:market.topic,closes_at:market.closes_at,source:market.source||'gemini',why:market.why,outcomes:[]});
  const event=events.get(id);
  let contract=event.outcomes.find(row=>row.id===market.id);
  if(!contract){
   contract={...market,event_ticker:id,source:market.source||'gemini',prices:{yes:market.prices?.yes??null,no:market.prices?.no??null},outcomes:[]};
   event.outcomes.push(contract);
  }
  const choices=Array.isArray(market.outcomes)?market.outcomes:sides.includes(market.outcome)?[{outcome:market.outcome,price:market.price,quote:market.quote,selectable:market.selectable,reason:market.reason}]:[];
  for(const choice of choices){
   if(!sides.includes(choice.outcome))continue;
   const position=contract.outcomes.findIndex(o=>o.outcome===choice.outcome);
   if(position===-1)contract.outcomes.push({...choice});
   else contract.outcomes[position]={...contract.outcomes[position],...choice};
   if(choice.price!=null)contract.prices[choice.outcome]=choice.price;
  }
 }
 return [...events.values()];
}

function tailoredEvents(suggestions){
 if(!Array.isArray(suggestions?.events))return groupSuggestedEvents(suggestions);
 const selected=new Map((suggestions.markets||[]).map(m=>[m.id,m]));
 return suggestions.events.map(event=>{
  const matched=(event.outcomes||[]).map(m=>selected.get(m.id)).filter(Boolean);
  return {...event,why:event.why||matched[0]?.why,outcomes:(event.outcomes||[]).map(m=>{
   const recommended=selected.get(m.id);
   return {...m,title:m.title||event.title,event_ticker:m.event_ticker||event.id,category:m.category||event.category,topic:m.topic||event.topic,source:event.source||'gemini',why:m.why||recommended?.why,...(recommended?.outcomes?{outcomes:recommended.outcomes}:{})};
  })};
 });
}

const searchable=value=>String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
export function filterMarketEvents(events,query=''){
 const terms=searchable(query).trim().split(/\s+/).filter(Boolean);
 if(!terms.length)return events;
 return events.filter(event=>{
  const context=searchable([event.title,event.category,event.topic,...(event.outcomes||[]).flatMap(m=>[m.label,m.title])].join(' '));
  return terms.every(term=>context.includes(term));
 });
}

export function orderMarketOutcomes(outcomes){
 return [...outcomes].sort((a,b)=>(marketProbability(b)??-1)-(marketProbability(a)??-1));
}

export function selectMarketEvents({suggestions,catalog,query='',demo=false}){
 const events=demo?demoMarketEvents:query.trim()?(catalog||[]):tailoredEvents(suggestions);
 return filterMarketEvents(events,query);
}
