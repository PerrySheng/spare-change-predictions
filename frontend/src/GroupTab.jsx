import React, {useEffect, useMemo, useRef, useState} from 'react';
import {
  ArrowLeft, ArrowRight, BookOpen, Check, ChevronDown, ChevronRight, Copy,
  ExternalLink, Link, LoaderCircle, LockKeyhole, MessageCircle, Plus,
  RefreshCw, Search, Send, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp,
  TrendingUp, Trophy, Users, X,
} from 'lucide-react';
import {API_BASE, api, post, money, closeDate} from './api';
import './group.css';
import SwarmChip from './SwarmChip';
import SwarmMascot from './SwarmMascot';

const query = user => '?user_id=' + encodeURIComponent(user.id);
const percent = value => value == null ? '—' : (value * 100).toLocaleString(undefined, {maximumFractionDigits: 1}) + '%';
const edge = value => value == null ? '—' : (value > 0 ? '+' : '') + (value * 100).toLocaleString(undefined, {maximumFractionDigits: 1}) + ' pts';
const price = value => (Number(value) * 100).toLocaleString(undefined, {maximumFractionDigits: 2}) + '¢';
const statusLabel = status => ({open: 'Picks open', locked: 'Picks locked', resolved: 'Results in', incomplete: 'Incomplete slip'}[status] || status);
const initials = name => name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
const localDate = () => {
  const time = new Date(Date.now() + 60 * 60 * 1000);
  return new Date(time.getTime() - time.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

function BusyButton({busy, children, className = 'group-primary', ...props}) {
  return <button className={className} {...props} disabled={busy || props.disabled}>
    {busy && <LoaderCircle size={16} className="spin"/>}{children}
  </button>;
}

function ErrorNotice({message, onDismiss}) {
  return message ? <div className="group-error" role="alert"><span>{message}</span><button aria-label="Dismiss error" onClick={onDismiss}><X size={15}/></button></div> : null;
}

export default function GroupTab({user, onResearch, onSwarm,initialInviteCode=''}) {
  const [squads, setSquads] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [form, setForm] = useState(initialInviteCode?'join':null);
  const [toast, setToast] = useState('');
  const [connection, setConnection] = useState('connecting');
  const alive = useRef(true);
  const selected = useRef(null);
  const lastEvent = useRef(0);
  const loadSequence = useRef(0);

  async function loadList() {
    const result = await api('/squads' + query(user));
    if (alive.current) setSquads(result);
    return result;
  }

  function acceptDetail(result) {
    if (!alive.current || selected.current !== result.id) return;
    setDetail(result);
    lastEvent.current = Math.max(lastEvent.current, ...result.events.map(event => event.id), 0);
    setSquads(previous => previous.some(squad => squad.id === result.id)
      ? previous.map(squad => squad.id === result.id ? result : squad) : [result, ...previous]);
  }

  async function loadDetail(id = selected.current, quiet = false) {
    if (!id) return;
    const sequence = ++loadSequence.current;
    try {
      const result = await api('/squads/' + id + query(user));
      if (sequence === loadSequence.current) acceptDetail(result);
    } catch (exception) {
      if (!quiet && alive.current && selected.current === id) setError(exception.message);
    }
  }

  useEffect(() => {
    alive.current = true;
    setLoading(true);
    setError('');
    loadList().catch(exception => {if (alive.current) setError(exception.message);})
      .finally(() => {if (alive.current) setLoading(false);});
    return () => {alive.current = false; loadSequence.current++;};
  }, [user.id]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(''), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (!activeId) return;
    let source;
    let refreshTimer;
    setConnection('connecting');
    if (typeof EventSource !== 'undefined') {
      source = new EventSource(API_BASE + '/squads/' + activeId + '/events' + query(user) + '&after=' + lastEvent.current);
      source.onopen = () => setConnection('live');
      source.onerror = () => setConnection('reconnecting');
      source.addEventListener('squad', event => {
        try {lastEvent.current = Math.max(lastEvent.current, JSON.parse(event.data).id);} catch {return;}
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(() => loadDetail(activeId, true), 150);
      });
    } else setConnection('polling');
    const poll = setInterval(() => {if (!document.hidden) loadDetail(activeId, true);}, 15000);
    return () => {source?.close(); clearInterval(poll); clearTimeout(refreshTimer);};
  }, [activeId, user.id]);

  function openSquad(squad) {
    selected.current = squad.id;
    lastEvent.current = Math.max(...squad.events.map(event => event.id), 0);
    setActiveId(squad.id); setDetail(squad); setError(''); setForm(null);
    loadDetail(squad.id);
  }

  function back() {
    selected.current = null; loadSequence.current++;
    setActiveId(null); setDetail(null); setError('');
    loadList().catch(exception => setError(exception.message));
  }

  async function action(key, path, data = {}) {
    setBusy(key); setError('');
    try {
      const result = await post(path, {user_id: user.id, ...data});
      if (result.id) {
        if (!selected.current) openSquad(result);
        else acceptDetail(result);
      }
      return result;
    } catch (exception) {
      if (alive.current) setError(exception.message);
      return null;
    } finally {if (alive.current) setBusy('');}
  }

  async function copyInvite() {
    try {await navigator.clipboard.writeText(detail.invite_code); setToast('Invite code copied.');}
    catch {setToast('Select and copy the invite code below.');}
  }

  return <section className="group-tab">
    <ErrorNotice message={error} onDismiss={() => setError('')}/>
    {toast && <div className="group-toast" role="status"><Check size={15}/>{toast}</div>}
    {activeId && detail ? <>
      <div className="group-detail-heading"><button className="group-back" onClick={back}><ArrowLeft size={16}/>Your squads</button><button className="group-icon" aria-label="Refresh squad" disabled={!!busy} onClick={() => loadDetail()}><RefreshCw size={16}/></button></div>
      <SquadDetail squad={detail} user={user} busy={busy} connection={connection} action={action} onReload={() => loadDetail()} copyInvite={copyInvite} onResearch={onResearch} onSwarm={onSwarm}/>
    </> : <>
      <div className="group-title"><div><p>Good company. Different perspectives.</p><h2>Better together.</h2></div><span className="group-title-icon"><Users size={24}/></span></div>
      <div className="group-intro"><span className="group-kicker"><span className="status-dot"/>YOUR SQUAD SLIP</span><h3>One friend.<br/>One pick.</h3><p>Bring your people, choose your sides, and see whose instincts beat the odds.</p><div className="group-intro-actions"><button className="group-primary" onClick={() => setForm(form === 'create' ? null : 'create')}><Plus size={16}/>Start a squad</button><button className="group-white" onClick={() => setForm(form === 'join' ? null : 'join')}><Link size={15}/>Join with code</button></div><span className="group-intro-note"><ShieldCheck size={13}/>Proposed picks. No funds move when you join.</span></div>
      {form === 'create' && <CreateForm busy={busy === 'create'} onClose={() => setForm(null)} onSubmit={data => action('create', '/squads', data)}/>}
      {form === 'join' && <JoinForm initialCode={initialInviteCode} busy={busy === 'join'} onClose={() => setForm(null)} onSubmit={data => action('join', '/squads/join', data)}/>}
      <div className="group-section-heading"><h3>Your squads</h3><button className="group-text" onClick={() => loadList().catch(exception => setError(exception.message))}><RefreshCw size={13}/>Refresh</button></div>
      {loading ? <div className="group-loading"><LoaderCircle size={19} className="spin"/>Finding your squads…</div> : squads.length ? <div className="group-squad-list">{squads.map(squad => <button className="group-squad-card" key={squad.id} onClick={() => openSquad(squad)}><div><span className={'group-status ' + squad.status}>{statusLabel(squad.status)}</span><h4>{squad.name}</h4><p>{squad.members.length}/{squad.member_limit} friends · {squad.legs.length} pick{squad.legs.length === 1 ? '' : 's'} · {money(squad.stake_cents)} proposed stake</p><span className="group-card-date">{squad.status === 'open' ? 'Locks ' : 'Lock time '}{closeDate(squad.lock_at)}</span></div><ChevronRight size={20}/></button>)}</div> : <div className="group-empty"><Users size={25}/><h4>Your first squad starts here.</h4><p>Create a slip or enter a friend’s invite code. Your real picks and conversations will live here.</p></div>}
      <p className="group-footnote">A squad slip records everyone’s proposed picks. Combined orders and testnet escrow require separately configured providers.</p>
    </>}
  </section>;
}

function CreateForm({onSubmit, onClose, busy}) {
  const [name, setName] = useState('');
  const [stake, setStake] = useState('15');
  const [memberLimit, setMemberLimit] = useState(3);
  const [lockAt, setLockAt] = useState(localDate);
  const [error, setError] = useState('');
  function submit(event) {
    event.preventDefault(); setError('');
    if (!/^\d+(\.\d{1,2})?$/.test(stake) || Number(stake) <= 0) {setError('Enter a positive dollar amount with at most two decimal places.'); return;}
    const date = new Date(lockAt);
    if (!Number.isFinite(date.getTime()) || date <= new Date()) {setError('Choose a future lock time.'); return;}
    onSubmit({name: name.trim(), stake_cents: Math.round(Number(stake) * 100), member_limit: Number(memberLimit), lock_at: date.toISOString()});
  }
  return <form className="group-form" onSubmit={submit}><div className="group-form-heading"><h3>Make it a group thing.</h3><button type="button" className="group-icon" aria-label="Close create form" onClick={onClose}><X size={16}/></button></div><ErrorNotice message={error} onDismiss={() => setError('')}/><label>Squad name<input autoFocus required maxLength={80} value={name} onChange={event => setName(event.target.value)} placeholder="Give your squad a name"/></label><div className="group-form-row"><label>Total proposed stake ($)<input required inputMode="decimal" value={stake} onChange={event => setStake(event.target.value)}/></label><label>Friends, including you<select value={memberLimit} onChange={event => setMemberLimit(event.target.value)}>{[2, 3, 4, 5, 6].map(number => <option key={number} value={number}>{number} friends</option>)}</select></label></div><label>Picks lock at · your local time<input required type="datetime-local" value={lockAt} onChange={event => setLockAt(event.target.value)}/></label><p className="group-form-note">Everyone can change their own pick and react until this time. An incomplete squad closes without settlement.</p><BusyButton busy={busy} type="submit">Create squad<ArrowRight size={16}/></BusyButton></form>;
}

function JoinForm({onSubmit, onClose, busy,initialCode=''}) {
  const [code, setCode] = useState(initialCode);
  return <form className="group-form" onSubmit={event => {event.preventDefault(); onSubmit({invite_code: code.trim()});}}><div className="group-form-heading"><h3>Pull up a chair.</h3><button className="group-icon" type="button" aria-label="Close join form" onClick={onClose}><X size={16}/></button></div><label>Your friend’s invite code<input autoFocus required maxLength={32} autoCapitalize="characters" value={code} onChange={event => setCode(event.target.value.toUpperCase())} placeholder="Enter invite code"/></label><BusyButton type="submit" busy={busy}>Join squad<ArrowRight size={16}/></BusyButton></form>;
}

function SquadDetail({squad, user, busy, connection, action, onReload, copyInvite, onResearch, onSwarm}) {
  const [picker, setPicker] = useState(false);
  const [section, setSection] = useState('slip');
  const editable = squad.status === 'open' && new Date(squad.lock_at) > new Date();
  const ownLeg = squad.legs.find(leg => leg.user_id === user.id);
  const complete = squad.members.length === squad.member_limit && squad.legs.length === squad.member_limit;
  const path = '/squads/' + squad.id;
  useEffect(() => {setPicker(false); setSection('slip');}, [squad.id]);
  return <>
    <div className="group-squad-hero"><div className="group-hero-top"><span className={'group-status ' + squad.status}>{statusLabel(squad.status)}</span><span className="group-stake">{money(squad.stake_cents)}<small>proposed stake</small></span></div><h2>{squad.name}</h2><div className="group-members">{squad.members.map(member => <span className="group-avatar" key={member.user_id} title={member.name}>{initials(member.name)}</span>)}{squad.members.length < squad.member_limit && <span className="group-open-slots">+{squad.member_limit - squad.members.length}</span>}<span>{squad.members.length}/{squad.member_limit} friends</span></div><div className="group-invite"><span>Invite code <strong>{squad.invite_code}</strong></span><button onClick={copyInvite} aria-label="Copy invite code"><Copy size={14}/></button></div></div>
    <div className="group-lock-note"><LockKeyhole size={15}/><div><strong>{editable ? 'A little time to change your mind.' : 'Your picks are frozen.'}</strong><p>{editable ? 'Swaps and reactions close ' : 'Lock time: '}{closeDate(squad.lock_at)}{squad.status === 'incomplete' ? '. The squad was incomplete and cannot settle.' : '.'}</p></div></div>
    <div className="group-view-tabs" role="tablist" aria-label="Squad views">{[['slip', 'The slip', Users], ['chat', 'Chat', MessageCircle], ['records', 'Track records', Trophy]].map(([key, label, Icon]) => <button id={'group-tab-' + key} role="tab" aria-controls={'group-panel-' + key} aria-selected={section === key} key={key} className={section === key ? 'selected' : ''} onClick={() => setSection(key)}><Icon size={15}/>{label}</button>)}</div>
    {section === 'slip' && <div id="group-panel-slip" role="tabpanel" aria-labelledby="group-tab-slip">
      <div className="group-section-heading"><div><h3>Everyone brings a perspective.</h3><p>{squad.legs.length}/{squad.member_limit} legs picked</p></div>{editable && <button className="group-mini-primary" disabled={!!busy} onClick={() => setPicker(!picker)}>{picker ? <X size={14}/> : <Plus size={14}/>} {picker ? 'Close' : ownLeg ? 'Swap mine' : 'My pick'}</button>}</div>
      {picker && <MarketPicker user={user} ownLeg={ownLeg} legs={squad.legs} busy={busy} onResearch={onResearch} onSwarm={onSwarm?market=>onSwarm(market,{defaultSquadId:squad.id}):null} onPick={async (market, outcome) => {const result = await action('pick', path + '/legs', {market_id: market.id, outcome, max_price: market.prices[outcome]}); if (result) setPicker(false);}}/>}
      <div className="group-legs">{squad.members.map(member => {
        const leg = squad.legs.find(row => row.user_id === member.user_id);
        const record = squad.leaderboard.find(row => row.user_id === member.user_id)?.record;
        return leg ? <LegCard key={member.user_id} leg={{...leg,squad_id:squad.id}} record={record} user={user} editable={editable} busy={busy} onResearch={onResearch} onSwarm={onSwarm?(market,options={})=>onSwarm(market,{defaultSquadId:squad.id,...options}):null} onAsk={async () => {const result = await action('ask-' + leg.id, path + '/swarm/ask', {leg_id: leg.id}); if (result) onSwarm({...leg, id: leg.market_id}, {runId: result.run_id, shareSquad: squad.name});}} onVote={data => action('vote-' + leg.id, path + '/votes', {leg_id: leg.id, ...data})}/> : <div className="group-awaiting" key={member.user_id}><span className="group-avatar">{initials(member.name)}</span><div><strong>{member.name}{member.user_id === user.id ? ' · you' : ''}</strong><p>{editable ? 'Their perspective is on the way.' : 'No leg was picked.'}</p></div>{editable && member.user_id === user.id && <button className="group-text" onClick={() => setPicker(true)}>Choose<ChevronRight size={15}/></button>}</div>;
      })}</div>
      {editable && squad.creator_id === user.id && <BusyButton className="group-outline" busy={busy === 'lock'} disabled={!complete || !!busy} onClick={() => action('lock', path + '/lock')}><LockKeyhole size={15}/>Lock everyone’s picks</BusyButton>}
      {editable && !complete && <p className="group-form-note">All {squad.member_limit} friends need to join and pick one leg before you can lock early.</p>}
      {!editable && squad.status !== 'incomplete' && <BusyButton className="group-outline" busy={busy === 'results'} disabled={!!busy} onClick={() => action('results', path + '/refresh')}><RefreshCw size={15}/>Check Gemini results</BusyButton>}
      <SettlementStatus squad={squad} user={user} onChange={onReload}/>
    </div>}
    {section === 'chat' && <div id="group-panel-chat" role="tabpanel" aria-labelledby="group-tab-chat"><SquadChat onOpenRun={data => onSwarm(null, {runId:data.run_id, squadId:squad.id})} events={squad.events} user={user} connection={connection} busy={busy === 'message'} onSend={body => action('message', path + '/messages', {body})}/></div>}
    {section === 'records' && <div id="group-panel-records" role="tabpanel" aria-labelledby="group-tab-records"><Leaderboard rows={squad.leaderboard} user={user}/></div>}
  </>;
}

export const marketTakenBy=(legs,userId,marketId,eventTicker)=>legs.find(leg=>(leg.market_id===marketId||(eventTicker&&leg.event_ticker===eventTicker))&&leg.user_id!==userId)||null;

function MarketPicker({user, ownLeg, legs=[],busy, onPick, onResearch,onSwarm}) {
  const [markets, setMarkets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  async function load() {setLoading(true); setError(''); try {setMarkets(await api('/squads/markets' + query(user)));} catch (exception) {setError(exception.message);} finally {setLoading(false);}}
  useEffect(() => {let live = true; api('/squads/markets' + query(user)).then(result => {if (live) setMarkets(result);}).catch(exception => {if (live) setError(exception.message);}).finally(() => {if (live) setLoading(false);}); return () => {live = false;};}, [user.id]);
  const filtered = markets.filter(market => (market.title + ' ' + market.label + ' ' + market.category).toLowerCase().includes(search.toLowerCase()));
  return <div className="group-market-picker"><div className="group-picker-heading"><div><span className="group-kicker">LIVE GEMINI BUY QUOTES</span><h4>{ownLeg ? 'A fresh perspective?' : 'What’s your call?'}</h4></div><button className="group-icon" aria-label="Refresh Gemini markets" disabled={loading} onClick={load}><RefreshCw size={15}/></button></div><p className="group-form-note">Yes means you expect this outcome. No means you expect it not to happen. Choosing records a proposed leg.</p><label className="group-search"><Search size={16}/><input aria-label="Search squad markets" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search a team, topic, or market"/></label><ErrorNotice message={error} onDismiss={() => setError('')}/>{loading ? <div className="group-loading"><LoaderCircle size={17} className="spin"/>Getting real market quotes…</div> : <div className="group-picker-list">{filtered.map(market => {const owner=marketTakenBy(legs,user.id,market.id,market.event_ticker);return <article className="group-pick-market" key={market.id}><div className="group-leg-meta"><span>{market.category}</span><span>{closeDate(market.closes_at)}</span></div><h4>{market.title}</h4>{market.label && market.label !== market.title && <p>{market.label}</p>}<div className="group-side-options">{['yes', 'no'].map(outcome => <button key={outcome} className={outcome + (ownLeg?.market_id === market.id && ownLeg?.outcome === outcome ? ' chosen' : '')} disabled={!!busy||!!owner||market.prices[outcome]==null} aria-label={`Choose ${outcome} for ${market.label || market.title}, ${price(market.prices[outcome])} Gemini buy quote`} onClick={() => onPick(market, outcome)}><span>{outcome === 'yes' ? 'Yes' : 'No'}</span><strong>{price(market.prices[outcome])}</strong>{ownLeg?.market_id === market.id && ownLeg?.outcome === outcome && <Check size={14}/>}</button>)}</div>{owner&&<p className="group-taken">{owner.user_name} picked this event first. Choose a different event.</p>}{onResearch && <button className="group-text group-research" onClick={() => onResearch({...market, outcome: 'yes'})}><BookOpen size={13}/>Read the background<ArrowRight size={12}/></button>}{onSwarm&&<SwarmChip user={user} market={market} onSwarm={onSwarm}/>}</article>})}{!filtered.length && <p className="group-no-results">{markets.length ? 'No markets match your search.' : 'No open instruments currently have valid Yes and No quotes.'}</p>}</div>}</div>;
}

export function LegCard({leg, record, user, editable, busy, onVote, onResearch, onSwarm, onAsk}) {
  const [reaction, setReaction] = useState(null);
  const [comment, setComment] = useState('');
  const ownVote = leg.votes.find(vote => vote.user_id === user.id);
  const category = record?.categories?.[leg.category.toLowerCase()];
  const market = {...leg, id: leg.market_id, price: leg.entry_price};
  async function send(event) {event.preventDefault(); const result = await onVote({reaction, comment}); if (result) {setReaction(null); setComment('');}}
  return <article className="group-leg-card"><div className="group-leg-person"><span className="group-avatar">{initials(leg.user_name)}</span><div><strong>{leg.user_name}{leg.user_id === user.id ? ' · you' : ''}</strong><span>{category?.edge_score == null ? 'No resolved ' + leg.category.toLowerCase() + ' picks yet' : edge(category.edge_score) + ' ' + leg.category.toLowerCase() + ' edge'}</span></div><span className={'group-leg-result ' + leg.status}>{leg.status === 'open' ? 'Pending' : leg.status === 'won' ? 'Hit' : leg.status === 'lost' ? 'Miss' : 'Void'}</span></div><div className="group-leg-meta"><span>{leg.category}</span><span>Closes {closeDate(leg.closes_at)}</span></div><h4>{leg.title}</h4>{leg.label && leg.label !== leg.title && <p className="group-leg-label">{leg.label}</p>}<div className="group-pick-line"><span className={'group-side ' + leg.outcome}>{leg.outcome.toUpperCase()} <strong>{price(leg.entry_price)}</strong></span><span>Gemini buy quote at pick time</span></div><div className="group-reactions">{[['agree', ThumbsUp, leg.agree_count], ['disagree', ThumbsDown, leg.disagree_count]].map(([key, Icon, count]) => <button disabled={!editable || !!busy} aria-pressed={ownVote?.reaction === key} className={ownVote?.reaction === key ? 'selected' : ''} key={key} onClick={() => {setReaction(reaction === key ? null : key); setComment(ownVote?.comment || '');}}><Icon size={14}/>{key === 'agree' ? 'Agree' : 'Disagree'}<strong>{count}</strong></button>)}</div>{reaction && editable && <form className="group-vote-form" onSubmit={send}><label>{reaction === 'agree' ? 'Backing this pick' : 'Seeing it differently'} · optional comment<input autoFocus value={comment} onChange={event => setComment(event.target.value)} maxLength={300} placeholder="What’s your thinking?"/></label><div><button type="button" className="group-text" onClick={() => setReaction(null)}>Cancel</button><BusyButton className="group-mini-primary" busy={busy === 'vote-' + leg.id} disabled={!!busy} type="submit">Post reaction<Send size={13}/></BusyButton></div></form>}{leg.votes.some(vote => vote.comment) && <div className="group-leg-comments">{leg.votes.filter(vote => vote.comment).map(vote => <p key={vote.user_id}><strong>{vote.user_name}</strong><span>{vote.reaction === 'agree' ? ' agrees' : ' disagrees'}: </span>{vote.comment}</p>)}</div>}<div className="group-leg-tools">{leg.swarm_research&&<button className="swarm-chip has-forecast" onClick={()=>onSwarm(null,{runId:leg.swarm_research.run_id,squadId:leg.squad_id})}><SwarmMascot size={20}/><span><strong>Swarm researched</strong><small>Your leg · Swarm contributes no money</small></span></button>}{onResearch && <button className="group-text" onClick={() => onResearch(market)}><BookOpen size={13}/>Read up</button>}{onSwarm && <SwarmChip user={user} market={market} onSwarm={onSwarm}/>}<BusyButton className="group-text" busy={busy === "ask-" + leg.id} disabled={!!busy || leg.status !== "open" || new Date(leg.closes_at) <= new Date()} onClick={onAsk}><Sparkles size={13}/>Ask the Swarm · share to chat</BusyButton></div></article>;
}

function SquadChat({events, user, connection, busy, onSend, onOpenRun}) {
  const [body, setBody] = useState('');
  const pane = useRef(null);
  const pinned = useRef(true);
  useEffect(() => {if (pinned.current && pane.current) pane.current.scrollTop = pane.current.scrollHeight;}, [events.length]);
  async function submit(event) {event.preventDefault(); if (!body.trim()) return; const result = await onSend(body.trim()); if (result) {setBody(''); pinned.current = true;}}
  const online = connection === 'live';
  return <div className="group-chat"><div className="group-section-heading"><h3>All the takes, together.</h3><span className={'group-live ' + (online ? 'connected' : '')}><i/>{online ? 'Live' : connection === 'reconnecting' ? 'Reconnecting' : connection === 'polling' ? 'Updating' : 'Connecting'}</span></div><p className="group-chat-intro">Picks, reactions, swaps, and shared reading appear here.</p><div className="group-chat-messages" ref={pane} onScroll={() => {const element = pane.current; pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < 50;}} aria-live="polite" aria-relevant="additions">{events.map(event => ['message','article','swarm_forecast','swarm_leg'].includes(event.type) ? <article className={'group-chat-bubble ' + (event.user_id === user.id ? 'mine' : '') + (['swarm_forecast','swarm_leg'].includes(event.type) ? ' group-swarm-chat' : '')} key={event.id}><div><strong>{event.user_name}</strong><time>{closeDate(event.created_at)}</time></div>{['swarm_forecast','swarm_leg'].includes(event.type) && event.data ? <><strong>{event.data.title}</strong><p>{event.body}</p><button className="swarm-chip has-forecast" onClick={()=>onOpenRun(event.data)}><Sparkles size={14}/><span><strong>Swarm {percent(event.data.selected_probability)} vs Gemini {percent(event.data.market_price)}</strong><small>{event.data.outcome.toUpperCase()} · quote at forecast time · view research</small></span><ExternalLink size={13}/></button><small>{event.data.note||"Research can be wrong. Shared for discussion."}</small></> : event.type === 'article' && event.data ? <><a className="group-article-link" href={event.data.url} target="_blank" rel="noopener noreferrer"><BookOpen size={16}/><span>{event.data.title}</span><ExternalLink size={13}/></a>{event.data.summary && <p>{event.data.summary}</p>}<span className="group-source-domain">{sourceDomain(event.data.url)}</span></> : <p>{event.body}</p>}</article> : <div className="group-chat-event" key={event.id}><span>{event.type === 'vote' ? <MessageCircle size={12}/> : event.type === 'lock' ? <LockKeyhole size={12}/> : event.type === 'result' ? <Trophy size={12}/> : <Users size={12}/>}</span><div><p>{event.body}</p><time>{closeDate(event.created_at)}</time></div></div>)}</div><form className="group-chat-compose" onSubmit={submit}><textarea required rows={2} maxLength={1000} aria-label="Message your squad" value={body} onChange={event => setBody(event.target.value)} placeholder="Drop a thought for the squad…"/><button type="submit" aria-label="Send squad message" disabled={busy || !body.trim()}>{busy ? <LoaderCircle className="spin" size={17}/> : <Send size={17}/>}</button></form><p className="group-form-note">Send as {user.name}. Messages are shared with this squad’s members.</p></div>;
}

function sourceDomain(url) {try {return new URL(url).hostname.replace(/^www\./, '');} catch {return 'Source';}}

function Leaderboard({rows, user}) {
  const [sort, setSort] = useState('edge_score');
  const [profile, setProfile] = useState(null);
  const sorted = useMemo(() => [...rows].sort((a, b) => (b.record[sort] ?? -Infinity) - (a.record[sort] ?? -Infinity) || a.name.localeCompare(b.name)), [rows, sort]);
  const friend = rows.find(row => row.user_id === profile);
  return <div className="group-records"><div className="group-section-heading"><div><h3>Can you beat the Swarm?</h3><p>Final locked picks across your squads</p></div><Trophy size={20}/></div><label className="group-sort">Sort by<select value={sort} onChange={event => setSort(event.target.value)}><option value="edge_score">Edge score</option><option value="hit_rate">Hit rate</option><option value="disagree_accuracy">Disagree accuracy</option></select></label><div className="group-leaderboard">{sorted.map((row, index) => <button className={'group-rank-row ' + (row.kind === 'swarm' ? 'swarm-player ' : '') + (profile === row.user_id ? 'selected' : '')} key={row.user_id} onClick={() => setProfile(profile === row.user_id ? null : row.user_id)}><span className="group-rank">{index + 1}</span><span className="group-avatar">{row.kind==='swarm'?<SwarmMascot size={26}/>:initials(row.name)}</span><span className="group-rank-name"><strong>{row.name}</strong><small>{row.record.wins} W · {row.record.losses} L · {row.record.void} void</small></span><span className={'group-rank-value ' + (row.record[sort] > 0 ? 'positive' : '')}><strong>{sort === 'edge_score' ? edge(row.record[sort]) : percent(row.record[sort])}</strong><small>{sort === 'edge_score' ? 'edge' : sort === 'hit_rate' ? 'hit rate' : 'disagree'}</small></span><ChevronDown size={14}/></button>)}</div>{friend && <FriendProfile friend={friend} user={user}/>}<div className="group-metric-explainer"><TrendingUp size={17}/><div><strong>What does edge mean?</strong><p>A hit scores 1, a miss scores 0. Subtract the Gemini buy price at pick time, then average. A positive edge means those picks beat their quoted odds.</p></div></div><p className="group-footnote">Void and unresolved picks stay out of edge scores. The Swarm uses one earliest forecast per market, completed before the first pick lock, from these members’ research. Sample sizes differ; open your profile for a comparison on the same markets.</p></div>;
}

function FriendProfile({friend, user}) {
  const record = friend.record;
  return <section className="group-friend-profile"><div className="group-profile-title"><span className="group-avatar">{initials(friend.name)}</span><div><h4>{friend.name}’s track record</h4><p>{record.streak.label}</p></div></div><div className="group-record-grid"><div><span>Hit rate</span><strong>{percent(record.hit_rate)}</strong></div><div><span>Average edge</span><strong>{edge(record.edge_score)}</strong></div><div><span>Disagree accuracy</span><strong>{percent(record.disagree_accuracy)}</strong><small>{record.disagree_correct}/{record.disagree_count} resolved disagreements</small></div><div><span>Still pending</span><strong>{record.pending}</strong><small>{record.void} voided picks</small></div></div><EdgeChart points={record.edge_over_time}/><SwarmComparison friend={friend} user={user}/><h5>By category</h5>{Object.keys(record.categories).length ? <div className="group-category-records">{Object.entries(record.categories).map(([category, value]) => <div key={category}><span>{category}</span><small>{value.wins} W / {value.losses} L / {value.void} void</small><strong>{edge(value.edge_score)}</strong></div>)}</div> : <p className="group-form-note">Category records appear after final picks are locked.</p>}</section>;
}

function SwarmComparison({friend, user}) {
  const record=friend.record;
  if(friend.kind==='swarm') return <div className="group-swarm-comparison"><h5>A research team, with a track record.</h5><p>{record.forecast_count} eligible forecasts · {record.resolved} scored · {record.unpriced_count} without a quote for the predicted side.</p><div className="group-swarm-scores"><div><span>Brier score · lower is better</span><strong>{record.brier_score==null?'—':record.brier_score.toFixed(3)}</strong></div><div><span>Average edge</span><strong>{edge(record.edge_score)}</strong></div></div><p>Only saved research and published Gemini outcomes count. The same hit-minus-quote formula applies to friends.</p></div>;
  const data=record.swarm_comparison;
  return <div className="group-swarm-comparison"><h5>{friend.user_id===user.id?'You':friend.name} vs the Swarm</h5>{data?.matched_count?<><p>{data.matched_count} shared resolved market{data.matched_count===1?'':'s'} in this squad. Both scores use the same outcomes and each side’s observed buy quote.</p><div className="group-swarm-scores"><div><span>{friend.user_id===user.id?'Your':friend.name+'’s'} edge</span><strong>{edge(data.friend_edge)}</strong></div><div><span>The Swarm’s edge</span><strong>{edge(data.swarm_edge)}</strong></div></div>{data.markets.map(m=><p key={m.market_id}><b>{m.title}</b><br/>{m.friend_side.toUpperCase()} pick · Swarm {m.swarm_side.toUpperCase()} · {percent(m.probability)} Yes estimate</p>)}</>:<p>No shared resolved markets yet. Research a leg before the squad locks, then check Gemini results once it resolves.</p>}</div>;
}

function EdgeChart({points}) {
  if (!points.length) return <div className="group-chart-empty"><TrendingUp size={24}/><p>No resolved picks yet.</p><span>The edge trend will use actual results as they arrive.</span></div>;
  const width = 300, height = 116, padding = 12;
  const values = points.map(point => point.average_edge);
  const low = Math.min(0, ...values), high = Math.max(0, ...values);
  const range = high - low || .1;
  const x = index => points.length === 1 ? width / 2 : padding + index / (points.length - 1) * (width - padding * 2);
  const y = value => padding + (high - value) / range * (height - padding * 2);
  const line = points.map((point, index) => `${x(index)},${y(point.average_edge)}`).join(' ');
  return <div className="group-edge-chart"><div><span>Average edge over time</span><strong>{edge(values.at(-1))}</strong></div><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Average edge across ${points.length} resolved picks. Latest ${edge(values.at(-1))}.`}><line x1={padding} x2={width - padding} y1={y(0)} y2={y(0)} stroke="#cdd8ec" strokeDasharray="4 4"/><polyline points={line} fill="none" stroke="#2d58dd" strokeWidth="2.5" strokeLinejoin="round"/>{points.map((point, index) => <circle key={point.leg_id || index} cx={x(index)} cy={y(point.average_edge)} r="3.5" fill="#2d58dd"><title>{closeDate(point.at)}: {edge(point.average_edge)}</title></circle>)}</svg><div className="group-chart-dates"><span>{closeDate(points[0].at)}</span><span>{points.length > 1 ? closeDate(points.at(-1).at) : '1 resolved pick'}</span></div></div>;
}

function SettlementStatus({squad, user, onChange}) {
  const plan = squad.payout_plan;
  const settled = squad.xrpl?.status === 'settled';
  const payoutAmount = settled ? testTokens : money;
  return <section className="group-settlement"><div className="group-section-heading"><h3>Orders & settlement</h3><ShieldCheck size={17}/></div><div className="group-provider-status"><span className="group-provider-icon"><Users size={16}/></span><div><strong>Combined Gemini order</strong><p>{squad.combo?.message || 'No combined order has been placed.'}</p></div><span>{squad.combo?.status === 'not_placed' ? 'Not placed' : squad.combo?.status}</span></div><XRPLPanel squad={squad} user={user} onChange={onChange}/>{plan && <div className="group-payout-plan"><h4>{settled ? 'Settled who owes what' : 'Calculated who owes what'}</h4><p>{settled ? 'The XRPL transaction journal confirms these test-token payouts.' : 'No payout has been made. This exact-cent plan uses the resolved legs.'}</p>{plan.members.map(member => <div key={member.user_id}><span>{squad.members.find(person => person.user_id === member.user_id)?.name || member.user_id}<small>{member.owes_cents ? 'Owes ' + payoutAmount(member.owes_cents) : member.receives_cents ? 'Receives ' + payoutAmount(member.receives_cents) : 'Collateral returned'}</small></span><strong>{payoutAmount(member.payout_cents)}<small>{settled ? 'confirmed test payout' : 'planned payout'}</small></strong></div>)}<footer>{payoutAmount(plan.total_payout_cents)} total = {payoutAmount(plan.total_collateral_cents)} collateral</footer></div>}</section>;
}

const testTokens = cents => (cents / 100).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' SPC';
const cancelDate = value => value ? closeDate(new Date((value + 946684800) * 1000).toISOString()) : 'Not set';

function XRPLPanel({squad, user, onChange}) {
  const [status, setStatus] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [escrow, setEscrow] = useState(squad.xrpl || null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState('');
  const [error, setError] = useState('');
  const mounted = useRef(true);
  const path = '/squads/' + squad.id + '/xrpl';
  async function load() {
    setLoading(true); setError('');
    const results = await Promise.allSettled([api('/xrpl/status'), api('/xrpl/wallet' + query(user)), api(path + query(user))]);
    if (!mounted.current) return;
    const setters = [setStatus, setWallet, setEscrow];
    const errors = [];
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') setters[index](result.value);
      else {errors.push(result.reason.message); if (index === 1) setWallet({status: 'unavailable'});}
    });
    setError([...new Set(errors)].join(' ')); setLoading(false);
  }
  useEffect(() => {mounted.current = true; setEscrow(squad.xrpl || null); return () => {mounted.current = false;};}, [squad.id]);
  useEffect(() => {if (squad.xrpl) setEscrow(squad.xrpl);}, [squad.xrpl?.status, squad.xrpl?.transactions?.length]);
  useEffect(() => {if (expanded) load();}, [expanded, squad.id, user.id]);
  async function mutate(key, endpoint) {
    setPending(key); setError('');
    try {
      await post(endpoint, {user_id: user.id});
      await load();
      if (onChange) await onChange();
    } catch (exception) {if (mounted.current) setError(exception.message);}
    finally {if (mounted.current) setPending('');}
  }
  const own = escrow?.escrows?.find(row => row.user_id === user.id);
  const complete = squad.members.length === squad.member_limit && squad.legs.length === squad.member_limit;
  const supported = squad.member_limit >= 3 && squad.member_limit <= 6;
  const stopped = ['unknown', 'releasing', 'settled', 'refunding', 'refunded'].includes(escrow?.status);
  const canLock = status?.configured && supported && complete && !stopped && (!own || own.status === 'failed');
  const canSettle = status?.configured && squad.creator_id === user.id && ['locked', 'releasing'].includes(escrow?.status);
  const canRefund = status?.configured && own?.status === 'locked' && !['releasing', 'settled', 'unknown'].includes(escrow?.status)
    && Number(status?.status?.ledger_close_time) > Number(own.cancel_after);
  return <div className="group-xrpl-panel"><button className="group-xrpl-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}><span className="group-provider-icon mint"><LockKeyhole size={16}/></span><span><strong>XRPL test-token escrow</strong><small>{escrow?.status === 'not_configured' ? 'No collateral locked · explore setup' : 'Status: ' + (escrow?.status || 'unavailable')}</small></span><ChevronDown size={15} className={expanded ? 'rotated' : ''}/></button>{expanded && <div className="group-xrpl-content"><div className="group-testnet-label"><ShieldCheck size={13}/>{status?.network || escrow?.network || 'Test network'} only · SPC test tokens</div><p className="group-form-note">SPC is a custom test token. It is not RLUSD or real dollars. Wallets are held by this demo’s server with encrypted keys.</p><ErrorNotice message={error} onDismiss={() => setError('')}/>{loading && <div className="group-loading"><LoaderCircle size={16} className="spin"/>Checking test-network state…</div>}{status && !status.configured && <div className="group-xrpl-setup-note"><strong>Testnet setup required</strong><p>{status.message}</p></div>}{status?.configured && <><div className="group-xrpl-wallet"><span>Your {status.network} wallet</span><strong>{wallet?.status === 'ready' ? (wallet.balance == null ? 'Balance unavailable' : wallet.balance + ' SPC') : 'Not created'}</strong>{wallet?.address && <code>{wallet.address}</code>}{wallet?.status === 'ready' && <small>{wallet.xrp_balance == null ? 'XRP balance unavailable' : wallet.xrp_balance + ' test XRP for network fees'}</small>}</div>{!status.issuer_ready && <BusyButton className="group-outline" busy={pending === 'setup'} disabled={!!pending} onClick={() => mutate('setup', '/xrpl/setup')}><Sparkles size={14}/>Prepare test-token issuer</BusyButton>}{wallet?.status === 'not_created' && <BusyButton className="group-outline" busy={pending === 'wallet'} disabled={!!pending} onClick={() => mutate('wallet', '/xrpl/wallet')}><Plus size={14}/>Create & fund my test wallet</BusyButton>}{!supported && <p className="group-form-note">Atomic escrow settlement supports squads of 3–6 friends. This squad has {squad.member_limit} slots.</p>}{supported && !complete && <p className="group-form-note">Everyone needs to join and pick a leg before collateral can be locked.</p>}{canLock && <><BusyButton busy={pending === 'lock'} disabled={!!pending} onClick={() => mutate('lock', path + '/lock')}><LockKeyhole size={14}/>Lock my test collateral</BusyButton><p className="group-form-note">First collateral lock freezes everyone’s picks and reactions. Each member locks their own SPC tokens.</p></>}{own && <div className="group-own-escrow"><div><span>Your collateral</span><strong>{testTokens(own.amount_cents)}</strong></div><span className="group-status">{own.status}</span><small>Refund eligible after {cancelDate(own.cancel_after)}, according to validated ledger time.</small></div>}{escrow?.escrows?.length > 0 && <div className="group-escrow-members">{escrow.escrows.map(row => <div key={row.user_id}><span>{squad.members.find(member => member.user_id === row.user_id)?.name || row.user_id}</span><strong>{testTokens(row.amount_cents)}</strong><small>{row.status}</small></div>)}</div>}{canSettle && <BusyButton className="group-outline" busy={pending === 'settle'} disabled={!!pending} onClick={() => mutate('settle', path + '/settle')}><Check size={14}/>Check results & settle test tokens</BusyButton>}{canRefund && <BusyButton className="group-outline" busy={pending === 'refund'} disabled={!!pending} onClick={() => mutate('refund', path + '/refund')}><ArrowLeft size={14}/>Refund my test escrow</BusyButton>}{escrow?.message && <p className="group-form-note">{escrow.message}</p>}{escrow?.status === 'unknown' && <div className="group-xrpl-setup-note"><strong>An operation needs reconciliation.</strong><p>Inspect the saved transaction links before any retry. The demo keeps uncertain funds reserved.</p></div>}</>}{escrow?.transactions?.length > 0 && <div className="group-xrpl-transactions"><h4>Transaction journal</h4>{escrow.transactions.map((transaction, index) => <a key={transaction.hash + ':' + index} href={transaction.explorer_url} target="_blank" rel="noopener noreferrer"><span><strong>{transaction.label || transaction.type}</strong><small>{transaction.hash.slice(0, 12)}… · {transaction.result}</small></span><ExternalLink size={13}/></a>)}</div>}<button className="group-text" disabled={loading || !!pending} onClick={load}><RefreshCw size={13}/>Refresh test-network state</button></div>}</div>;
}
