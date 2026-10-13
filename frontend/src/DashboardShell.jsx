import React from 'react';
import {Coins,UsersRound,Newspaper,Plus,ArrowUpRight,Wallet,TrendingUp,ShieldCheck,Activity} from 'lucide-react';
import {money} from './api';
import SwarmMascot from './SwarmMascot';
import SpotlightCard from './reactbits/SpotlightCard';

export function DashboardSidebar({user,tab,page,mode,onNavigate,onAddPurchase}){
 return <aside className="companion app-sidebar">
  <a className="wordmark sidebar-brand" href="/"><span className="mark"><Coins size={24}/></span>spare<span className="wordmark-dot">.</span></a>
  <p className="sidebar-description">Small change. Shared perspective.</p>
  {user&&<><nav className="sidebar-navigation" aria-label="Desktop navigation">{[['spare','Spare',Wallet],['group','Group betting',UsersRound],['news','News',Newspaper]].map(([id,label,Icon])=><button key={id} className={tab===id?'active':''} aria-current={tab===id?'page':undefined} onClick={()=>onNavigate(id)}><Icon size={20}/><span>{label}</span><ArrowUpRight size={15}/></button>)}</nav><div className="sidebar-secondary"><button className={tab==='spare'&&page==='feed'?'active':''} onClick={()=>onNavigate('spare','feed')}><Activity size={17}/>Activity</button><button className={tab==='spare'&&page==='pot'?'active':''} onClick={()=>onNavigate('spare','pot')}><TrendingUp size={17}/>Your pot</button></div><button className="sidebar-add" onClick={onAddPurchase}><Plus size={18}/>Add a purchase</button></>}
  <div className="sidebar-swarm"><SwarmMascot size={46}/><strong>Meet Swarm</strong><p>Four research perspectives.<br/>You make the call.</p><span>Research from market cards</span></div>
  <footer className="sidebar-footer"><span><ShieldCheck size={15}/>{mode==='sandbox'?'Sandbox test funds':'Paper mode'}</span>{user&&<div className="sidebar-profile"><span>{user.name?.slice(0,1)||'S'}</span><div><strong>{user.name}</strong><small>Your Spare workspace</small></div></div>}</footer>
 </aside>;
}

export function BalanceOverview({dashboard}){
 return <section className="balance-overview" aria-label="Your balances">
  {[["available_cents","Available change",Wallet,"Ready for your next pick","available"],["savings_cents","Savings",ShieldCheck,"Set aside, little by little","saved"],["market_value_cents","Market value",TrendingUp,"Current value of your positions","positions"]].map(([key,title,Icon,note,kind])=><SpotlightCard as="article" className={'balance-card '+kind} key={key} spotlightColor={kind==='available'?'#57d6a1':'#7da7ff'} intensity={.09} borderGlow={.3} flare={false} grain={0} style={{'--spotlight-card-surface':'var(--surface)','--spotlight-card-border':'var(--line)','--spotlight-card-shadow':'none'}}><div className="balance-label"><span>{title}</span><Icon size={18}/></div><strong className={dashboard?.[key]==null?'balance-unavailable':''}>{money(dashboard?.[key])}</strong><p>{note}</p></SpotlightCard>)}
 </section>;
}
