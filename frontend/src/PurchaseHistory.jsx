import React,{useState} from 'react';
import {ReceiptText,ChevronRight} from 'lucide-react';
import {money,closeDate} from './api';

export const purchaseHistoryRows=feed=>feed.filter(p=>p.is_purchase!==false&&p.roundup_cents>0);
const nameOf=p=>p.merchant?.trim()||'Purchase';

export default function PurchaseHistory({feed,onChoose}){
 const [shown,setShown]=useState(6);
 const purchases=purchaseHistoryRows(feed);
 const total=purchases.filter(p=>p.allocation!=='removed').reduce((sum,p)=>sum+p.roundup_cents,0);
 return <>
  <div className="feed-summary"><ReceiptText size={24}/><div><strong>{money(total)}</strong><p>Change from {purchases.length} purchase{purchases.length===1?'':'s'}</p></div></div>
  {purchases.length?<><div className="purchase-feed">{purchases.slice(0,shown).map(p=><button className="purchase-row" key={p.id} disabled={p.allocation!=='pending'} onClick={()=>onChoose(p)}><span className="merchant-avatar">{nameOf(p)[0]}</span><div><strong>{nameOf(p)}</strong><p>{closeDate(p.created_at)} · {money(p.amount_cents)}</p><span className={'allocation-label '+p.allocation}>{p.allocation==='pending'?'Choose where it goes':p.allocation==='savings'?'Added to savings':p.allocation==='market'?'Market position':p.allocation==='order_pending'?'Order being verified':p.allocation==='rollover'?'Held for a future pick':'Removed'}</span>{p.notice&&<small className="error-text">{p.notice}</small>}</div><div className="row-change">+{p.roundup_cents}¢{p.allocation==='pending'&&<ChevronRight size={17}/>}</div></button>)}</div>{purchases.length>shown&&<button className="secondary" onClick={()=>setShown(value=>value+6)}>Show more purchases · {purchases.length-shown} remaining</button>}</>:<div className="empty"><ReceiptText size={25}/><h3>No purchase change yet.</h3><p>Purchases that generate change appear here. Interest charges and zero-cent entries are hidden.</p></div>}
  <p className="fine-print">Showing {Math.min(shown,purchases.length)} of {purchases.length} purchases with change.</p>
 </>;
}
