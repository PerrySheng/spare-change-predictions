import React,{useCallback,useEffect,useId,useRef,useState} from 'react';
import {Search,X,Check,ChevronDown,BookOpen,Sparkles,LoaderCircle,Info,FlaskConical,Bitcoin,Trophy,Flag,CloudSun,Music,ChartNoAxesCombined,TrendingUp} from 'lucide-react';
import {api,closeDate,money} from './api';
import SwarmChip from './SwarmChip';
import {marketProbability,orderMarketOutcomes,selectMarketEvents,sideChoice} from './marketEvents.js';
import './marketBrowser.css';
import SpotlightCard from './reactbits/SpotlightCard';

const icons={crypto:Bitcoin,sports:Trophy,politics:Flag,weather:CloudSun,entertainment:Music,economy:ChartNoAxesCombined};
const quoteLabel=value=>value==null||!Number.isFinite(Number(value))||Number(value)<=0||Number(value)>=1?'No quote':`${(Number(value)*100).toLocaleString('en-US',{maximumFractionDigits:2})}¢`;
const percent=value=>value==null?'—':`${(value*100).toLocaleString('en-US',{maximumFractionDigits:1})}%`;
const isDemo=market=>market.source==='demo'||String(market.id).startsWith('demo-');

/*
 * ClickSpark is adapted from React Bits by David Haz:
 * https://reactbits.dev/animations/click-spark
 * https://github.com/DavidHDev/react-bits/blob/main/src/content/Animations/ClickSpark/ClickSpark.jsx
 * Adaptations: render only on a selection, stop the frame loop after the burst,
 * honor reduced motion, support keyboard clicks, and ignore disabled controls.
 *
 * MIT + Commons Clause License Condition v1.0
 * Copyright (c) 2026 David Haz
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, and distribute the Software as part of
 * an application, website, or product, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * Commons Clause Restriction
 * You may use this Software, including for any commercial purpose, so long as
 * you do not sell, sublicense, or redistribute the components themselves-
 * whether alone, in a bundle, or as a ported version.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
function ClickSpark({children}){
 const canvas=useRef(null),frame=useRef(null);
 useEffect(()=>()=>{if(frame.current!=null)cancelAnimationFrame(frame.current)},[]);
 function spark(event){
  const button=event.target.closest?.('.mb-quote');
  if(!button||button.disabled||window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const surface=canvas.current,context=surface?.getContext('2d');
  if(!context)return;
  if(frame.current!=null)cancelAnimationFrame(frame.current);
  const rect=surface.getBoundingClientRect(),buttonRect=button.getBoundingClientRect(),ratio=Math.min(window.devicePixelRatio||1,2);
  surface.width=Math.ceil(rect.width*ratio);surface.height=Math.ceil(rect.height*ratio);
  context.setTransform(ratio,0,0,ratio,0,0);
  const x=(event.detail?event.clientX:buttonRect.left+buttonRect.width/2)-rect.left;
  const y=(event.detail?event.clientY:buttonRect.top+buttonRect.height/2)-rect.top;
  const start=performance.now(),color=button.dataset.side==='no'?'#fc8c95':'#57d6a1';
  function draw(now){
   context.clearRect(0,0,rect.width,rect.height);
   const progress=Math.min((now-start)/360,1),eased=progress*(2-progress);
   if(progress>=1){frame.current=null;return;}
   context.strokeStyle=color;context.lineWidth=1.6;context.globalAlpha=1-progress;
   for(let i=0;i<7;i++){
    const angle=2*Math.PI*i/7,distance=eased*20,length=7*(1-eased);
    context.beginPath();context.moveTo(x+distance*Math.cos(angle),y+distance*Math.sin(angle));
    context.lineTo(x+(distance+length)*Math.cos(angle),y+(distance+length)*Math.sin(angle));context.stroke();
   }
   frame.current=requestAnimationFrame(draw);
  }
  frame.current=requestAnimationFrame(draw);
 }
 return <div className="mb-spark" onClick={spark}><canvas ref={canvas} className="mb-spark-canvas" aria-hidden="true"/>{children}</div>;
}

function QuoteButtons({market,onBet,selected,disabled,demo}){
 return <div className="mb-quotes">{['yes','no'].map(side=>{
  const choice=sideChoice(market,side),pressed=selected===`${market.id}:${side}`,label=side==='yes'?'Yes':'No';
  const unavailable=choice.reason==='unaffordable'?'Above your budget':'Quote unavailable';
  return <button type="button" key={side} data-side={side} className={`mb-quote mb-${side}${pressed?' mb-selected':''}`} disabled={disabled||!choice.available||!onBet} aria-pressed={pressed} aria-label={`${label} for ${market.label||market.title}, ${choice.available?quoteLabel(choice.price):`${quoteLabel(choice.price)}. ${unavailable}`}`} onClick={()=>onBet(market,side,{demo})}>
   <span>{label}</span><strong>{quoteLabel(choice.price)}</strong>{pressed&&<Check size={12} aria-hidden="true"/>}
   {!choice.available&&<small>{unavailable}</small>}
  </button>;
 })}</div>;
}

function ResearchActions({market,user,onResearch,onSwarm,disabled}){
 if(isDemo(market))return null;
 return <div className="mb-research-actions">
  {onResearch&&<button type="button" disabled={disabled} onClick={()=>onResearch(market)}><BookOpen size={13}/><span>Read in News</span></button>}
  {user&&onSwarm&&!disabled&&<SwarmChip user={user} market={market} onSwarm={onSwarm}/>}
 </div>;
}

function OutcomeResearch({market,...props}){
 const [open,setOpen]=useState(false);
 return <details className="mb-outcome-research" onToggle={event=>setOpen(event.currentTarget.open)}><summary><BookOpen size={11}/>Research {market.label||'outcome'}<ChevronDown size={11}/></summary>{open&&<ResearchActions market={market} {...props}/>}</details>;
}

export function MarketEventCard({event,user,onBet,onResearch,onSwarm,selected='',disabled=false}){
 const [expanded,setExpanded]=useState(false),outcomeId=useId();
 const outcomes=orderMarketOutcomes(event.outcomes||[]),multiple=outcomes.length>1,demo=isDemo(event),visible=expanded?outcomes:outcomes.slice(0,4);
 const Icon=icons[event.topic]||TrendingUp,chosen=outcomes.some(m=>selected.startsWith(`${m.id}:`));
 return <SpotlightCard as="article" spotlightColor="#7da7ff" intensity={.07} borderGlow={.22} flare={false} style={{'--spotlight-card-surface':'var(--surface)','--spotlight-card-border':'var(--line)','--spotlight-card-shadow':'none'}} className={`mb-event${chosen?' mb-event-selected':''}${demo?' mb-demo-event':''}`}>
  <div className="mb-event-meta"><span className={`mb-topic mb-topic-${event.topic}`}><Icon size={14}/>{event.category||event.topic||'Market'}</span>{demo?<span className="mb-source mb-demo-source"><FlaskConical size={11}/>Demo</span>:<span className="mb-source">Gemini</span>}</div>
  <h4>{event.title}</h4>
  {event.why&&!demo&&<p className="mb-why"><Sparkles size={11}/>{event.why}</p>}
  <ClickSpark>
   {multiple?<>
    <div className="mb-table-label"><span>{outcomes.length} outcomes</span><span>Chance</span></div>
    <div id={outcomeId} className="mb-outcomes">{visible.map(m=>{
     const probability=marketProbability(m),contract={...m,title:m.title||event.title,event_ticker:m.event_ticker||event.id,topic:m.topic||event.topic,category:m.category||event.category};
     return <div className={`mb-outcome${selected.startsWith(`${m.id}:`)?' mb-outcome-selected':''}`} key={m.id}>
      <div className="mb-outcome-label"><strong>{m.label||m.title}</strong><span className="mb-probability" aria-label={probability==null?'Implied chance unavailable':`${percent(probability)} implied chance`}>{percent(probability)}</span></div>
      <QuoteButtons market={contract} onBet={onBet} selected={selected} disabled={disabled} demo={demo}/>
      {!demo&&(onResearch||onSwarm)&&<OutcomeResearch market={contract} user={user} onResearch={onResearch} onSwarm={onSwarm} disabled={disabled}/>}
     </div>;
    })}</div>
   </>:outcomes[0]&&<>
    {outcomes[0].label&&outcomes[0].label!==event.title&&<p className="mb-binary-label">{outcomes[0].label}</p>}
    <div className="mb-binary-chance"><strong>{percent(marketProbability(outcomes[0]))}</strong><span>{marketProbability(outcomes[0])==null?'Implied chance unavailable':'Current implied chance'}</span><span className="mb-chance-track" aria-hidden="true"><i style={{width:`${(marketProbability(outcomes[0])||0)*100}%`}}/></span></div>
    <QuoteButtons market={{...outcomes[0],title:outcomes[0].title||event.title,event_ticker:outcomes[0].event_ticker||event.id,topic:outcomes[0].topic||event.topic,category:outcomes[0].category||event.category}} onBet={onBet} selected={selected} disabled={disabled} demo={demo}/>
   </>}
  </ClickSpark>
  {multiple&&outcomes.length>4&&<button type="button" className="mb-show-more" aria-expanded={expanded} aria-controls={outcomeId} onClick={()=>setExpanded(v=>!v)}>{expanded?'Show fewer outcomes':`Show ${outcomes.length-4} more outcomes`}<ChevronDown size={13} className={expanded?'mb-rotated':''}/></button>}
  {!multiple&&!demo&&outcomes[0]&&<ResearchActions market={outcomes[0]} user={user} onResearch={onResearch} onSwarm={onSwarm} disabled={disabled}/>}
  <div className="mb-event-footer">{demo?<span>Illustrative prices</span>:<span>{event.closes_at?`Closes ${closeDate(event.closes_at)}`:'Closing time not published'}</span>}<span>{multiple?'Independent Yes / No quotes':'Yes / No quotes'}</span></div>
 </SpotlightCard>;
}

export default function MarketBrowser({suggestions,user,onBet,onResearch,onSwarm,disabled=false,loading:tailoredLoading=false}){
 const [visibleCount,setVisibleCount]=useState(24);
 const [query,setQuery]=useState(''),[demo,setDemo]=useState(false),[catalog,setCatalog]=useState(null),[status,setStatus]=useState('idle'),[error,setError]=useState(''),[selected,setSelected]=useState('');
 const mounted=useRef(true),inFlight=useRef(false),catalogLoaded=useRef(false),searchId=useId(),descriptionId=useId();
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
 useEffect(()=>{setVisibleCount(24)},[query,demo]);
 const searching=Boolean(query.trim());
 const loadCatalog=useCallback(async()=>{
  if(inFlight.current||catalogLoaded.current)return;
  inFlight.current=true;setStatus('loading');setError('');
  try{
   const data=await api('/markets/events');
   if(data.source!=='gemini'||!Array.isArray(data.events))throw new Error('The market catalog returned an unreadable response.');
   catalogLoaded.current=true;
   if(mounted.current){setCatalog(data.events);setStatus('ready');}
  }catch(error){if(mounted.current){setError(error.message);setStatus('error');}}
  finally{inFlight.current=false;}
 },[]);
 useEffect(()=>{if(searching&&!demo&&status==='idle')loadCatalog()},[searching,demo,status,loadCatalog]);
 const events=selectMarketEvents({suggestions,catalog,query,demo});
 const loading=!demo&&(searching?(status==='idle'||status==='loading'):tailoredLoading);
 function choose(market,side,meta){setSelected(`${market.id}:${side}`);onBet?.(market,side,meta);}
 return <section className="market-browser" aria-label="Choose a prediction market" data-source={demo?'demo':'gemini'}>
  <div className="mb-search-header"><label htmlFor={searchId}>Search markets</label><button type="button" className={`mb-demo-toggle${demo?' mb-demo-active':''}`} aria-pressed={demo} onClick={()=>{setDemo(v=>!v);setSelected('')}}><FlaskConical size={12}/>Demo examples</button></div>
  <div className="mb-search-field"><Search size={16} aria-hidden="true"/><input id={searchId} type="search" autoComplete="off" placeholder="Events, topics, or outcomes" value={query} aria-describedby={descriptionId} onChange={event=>setQuery(event.target.value)}/>{query&&<button type="button" aria-label="Clear market search" onClick={()=>setQuery('')}><X size={15}/></button>}</div>
  <p id={descriptionId} className="mb-search-description">{demo?'Demo examples use illustrative prices. Choices open a demo preview.':'Search all open Gemini markets, or explore your tailored picks below.'}</p>
  {demo&&<p className="mb-demo-notice"><FlaskConical size={14}/><span>Demo examples · sample events and prices</span></p>}
  <div className="mb-results-heading"><h3>{demo?'Try a perspective':searching?'Search results':'Picked for you'}</h3><span role="status" aria-live="polite">{loading?(searching?'Loading catalog…':'Finding picks…'):`${events.length} event${events.length===1?'':'s'}`}</span></div>
  {loading?<div className="mb-loading" role="status"><LoaderCircle size={17} className="mb-spinner"/><span>{searching?'Loading open Gemini markets…':'Finding markets that fit your change…'}</span></div>:!demo&&searching&&status==='error'?<div className="mb-state mb-error" role="alert"><Info size={17}/><div><strong>Market search is unavailable</strong><p>{error}</p><button type="button" onClick={()=>setStatus('idle')}>Try again</button></div></div>:events.length?<div className="mb-events" key={demo?'demo':'gemini'}>{events.slice(0,visibleCount).map(event=><MarketEventCard key={event.id} event={event} user={user} onBet={onBet?choose:null} onResearch={onResearch} onSwarm={onSwarm} selected={selected} disabled={disabled}/>)}</div>:<div className="mb-state"><Search size={18}/><div><strong>{searching?'No matching events':'No tailored markets available'}</strong><p>{searching?'Try a different event, topic, or outcome.':suggestions?.reason==='paused'?'Market picks are paused. You can still browse the catalog.':'Search the open catalog to explore more events.'}</p></div></div>}
  {events.length>visibleCount&&!loading&&<button className="mb-more-events" type="button" onClick={()=>setVisibleCount(value=>value+24)}>Show more markets <span>{events.length-visibleCount} remaining</span></button>}
  {suggestions?.budget_cents!=null&&!demo&&!searching&&<p className="mb-budget">{money(suggestions.budget_cents)} available for your perspective. Your final quote includes fees.</p>}
 </section>;
}
