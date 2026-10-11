import React from 'react';
import {ArrowUpRight} from 'lucide-react';
import {estimateEarnings,actualQuoteEarnings,formatBetMoney,formatWin} from './betMath';
import './betPanel.css';

const count=new Intl.NumberFormat('en-US',{maximumFractionDigits:3});
const chance=new Intl.NumberFormat('en-US',{maximumFractionDigits:1});

export default function EarningsPreview({amountCents,price,outcome,quote,invalid=false}){
 const estimate=estimateEarnings(amountCents,price),actual=actualQuoteEarnings(quote);
 const updateKey=estimate?`${outcome}:${amountCents}:${price}`:'unavailable';
 return <div className={'earnings-preview'+(invalid?' invalid':'')}>
  <div className="earnings-topline"><span>If {outcome==='no'?'No':'Yes'} wins</span>{estimate&&<span>{chance.format(estimate.impliedChancePercent)}% implied chance</span>}</div>
  <div className="earnings-live" role="status" aria-live="polite" aria-atomic="true">
   {estimate?<strong key={updateKey} className="earnings-number">Win {formatBetMoney(estimate.payoutCents)} <span>({estimate.profitCents>=0?'+':''}{formatBetMoney(estimate.profitCents)})</span><ArrowUpRight size={19} aria-hidden="true"/></strong>:<strong className="earnings-unavailable">Win estimate unavailable</strong>}
  </div>
  {estimate&&<p className="earnings-contracts">{count.format(estimate.contracts)} estimated contracts at {formatBetMoney(Number(price)*100)} each</p>}
  <p className="earnings-note">Estimate before fees, assuming fractional contracts. Payout includes your stake; parentheses show profit.</p>
  {actual&&<div className="earnings-executable"><div><span>Current whole-contract quote</span><strong>{formatWin(actual)}</strong></div><p>{actual.contracts} contract{actual.contracts===1?'':'s'} · {formatBetMoney(actual.totalCents)} total, including {formatBetMoney(actual.feeCents)} estimated fee.</p></div>}
 </div>;
}
