import React,{useEffect,useState} from 'react';
import {Network,ArrowUpRight} from 'lucide-react';
import {api} from './api';
import {matchingForecast} from './swarmState';
import './swarmChip.css';
import SwarmMascot from './SwarmMascot';
const pct=n=>(n*100).toFixed(0)+'%';

// Cache reads only. Model calls start exclusively from an explicit run/ask.
export default function SwarmChip({user,market,onSwarm}){
 const [run,setRun]=useState(null),[unavailable,setUnavailable]=useState(false);
 const side=market.outcome||'yes';
 useEffect(()=>{let alive=true,sequence=0;
  async function load(){const current=++sequence;try{const data=await api(`/swarm/markets/${encodeURIComponent(market.id)}?user_id=${encodeURIComponent(user.id)}&outcome=${side}`);if(alive&&current===sequence){setRun(data.run);setUnavailable(false)}}catch{if(alive&&current===sequence){setRun(null);setUnavailable(true)}}}
  load();window.addEventListener('swarm-saved',load);
  const interval=setInterval(()=>{if(!document.hidden)load()},60000);
  return()=>{alive=false;clearInterval(interval);window.removeEventListener('swarm-saved',load)};
 },[user.id,market.id,side]);
 const saved=matchingForecast(run,user.id,market.id,side);
 return <button className={'swarm-chip '+(saved?'has-forecast':'')} onClick={()=>onSwarm(market,saved?{runId:saved.id}:{})} title={saved?`Saved ${new Date(saved.completed_at).toLocaleString()}. Quote at forecast time.`:unavailable?'Saved research could not be loaded. Open the research workspace.':'Open the research workspace'}>
  <SwarmMascot size={20}/>{saved?<span><strong>Swarm {pct(saved.result.selected_probability)}</strong><small>vs Gemini {pct(saved.result.market_price)} · {side.toUpperCase()} at forecast time</small></span>:<span>Swarm research</span>}<ArrowUpRight size={13}/>
 </button>;
}
