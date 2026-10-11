import React,{useState} from 'react';
import {Plus,LoaderCircle,Check} from 'lucide-react';
import {api,post} from './api';
import SwarmMascot from './SwarmMascot';

export default function SwarmLegPicker({user,run,defaultSquadId}){
 const [open,setOpen]=useState(false),[squads,setSquads]=useState([]),[squadId,setSquadId]=useState(''),[market,setMarket]=useState(null),[side,setSide]=useState(run.outcome||'yes'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[added,setAdded]=useState('');
 const squad=squads.find(s=>s.id===squadId);
 const taken=squad?.legs.find(l=>(l.market_id===run.market_id||(market?.event_ticker&&l.event_ticker===market.event_ticker))&&l.user_id!==user.id);
 async function load(){
  setOpen(true);setBusy(true);setError('');
  try{
   const [all,catalog]=await Promise.all([api('/squads?user_id='+encodeURIComponent(user.id)),api('/markets/events')]);
   const available=all.filter(s=>s.status==='open'&&new Date(s.lock_at)>new Date()&&!s.xrpl?.escrows?.length);
   setSquads(available);setSquadId(available.some(s=>s.id===defaultSquadId)?defaultSquadId:available[0]?.id||'');
   setMarket(catalog.events.flatMap(e=>e.outcomes).find(m=>m.id===run.market_id)||null);
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function add(event){
  event.preventDefault();setBusy(true);setError('');
  try{
   await post('/squads/'+encodeURIComponent(squadId)+'/legs',{user_id:user.id,market_id:run.market_id,outcome:side,max_price:market.prices[side],swarm_run_id:run.id});
   setAdded(squad.name);setOpen(false);
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return <div className="swarm-leg-picker"><div className="swarm-leg-heading"><SwarmMascot size={28}/><div><strong>Make your own call.</strong><p>You choose the side and fund your own leg. Swarm contributes no money.</p></div></div>
 {added&&<p role="status" className="swarm-leg-added"><Check size={15}/>Added as your leg in {added}.</p>}
 {!open?<button className="secondary" onClick={load}><Plus size={16}/>{added?'Choose again':'Use as my squad leg'}</button>:<form onSubmit={add}>
 {busy&&!market&&<p><LoaderCircle size={15} className="spin"/>Getting your squads and current market quotes…</p>}
 {error&&<p className="notice error" role="alert">{error}</p>}
 {!busy&&!squads.length&&<p>Create or join an open squad in Group Betting first.</p>}
 {squads.length>0&&<><label>Choose a squad<select value={squadId} onChange={e=>setSquadId(e.target.value)}>{squads.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
 <fieldset><legend>Your choice</legend>{['yes','no'].map(value=><button type="button" key={value} aria-pressed={side===value} disabled={busy||!market?.prices?.[value]} onClick={()=>setSide(value)}>{value.toUpperCase()} {market?.prices?.[value]!=null?Math.round(Number(market.prices[value])*100)+'¢':'—'}</button>)}</fieldset>
 {taken&&<p role="status">{taken.user_name} picked this event first. Its opposite sides and other outcomes are reserved.</p>}
 {!market&&!busy&&<p>This market is no longer available with current quotes.</p>}
 <button className="primary" type="submit" disabled={busy||!!taken||!squadId||!market?.prices?.[side]}>{busy?<LoaderCircle size={16} className="spin"/>:<Plus size={16}/>}Add my {side.toUpperCase()} leg</button></>}
 <button type="button" className="secondary" disabled={busy} onClick={()=>setOpen(false)}>Cancel</button>
 </form>}
 </div>;
}
