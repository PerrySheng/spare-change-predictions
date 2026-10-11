const dollars=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'});
const validCents=value=>Number.isSafeInteger(value)&&value>0;

export function parseBetAmount(input){
  const raw=String(input??'').trim().replace(/^\$\s*/, '');
  if(!/^(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{0,2})?|\.\d{1,2})$/.test(raw)) return null;
  const [whole='0',fraction='']=raw.replaceAll(',','').split('.');
  const cents=Number(whole||'0')*100+Number(fraction.padEnd(2,'0'));
  return validCents(cents)&&cents<=100_000_000?cents:null;
}

function usablePrice(value){
  if(value==null||typeof value==='boolean'||String(value).trim()==='') return null;
  const number=Number(value);
  return Number.isFinite(number)&&number>0&&number<1?number:null;
}

export function outcomePrice(market,side){
  if(!['yes','no'].includes(side)) return null;
  const direct=market?.prices?.[side];
  const published=direct??market?.outcomes?.find(item=>item.outcome===side)?.price;
  return usablePrice(published);
}

export function estimateEarnings(amountCents,publishedPrice){
  const price=usablePrice(publishedPrice);
  if(!validCents(amountCents)||price==null) return null;
  // Dividing integer cents by price preserves the half-cent boundary in $0.73 / $0.40.
  const rawPayoutCents=amountCents/price;
  if(!Number.isFinite(rawPayoutCents)||rawPayoutCents>Number.MAX_SAFE_INTEGER) return null;
  return {
    contracts:amountCents/(price*100),
    payoutCents:Math.round(rawPayoutCents+1e-9),
    profitCents:Math.round(rawPayoutCents-amountCents+1e-9),
    impliedChancePercent:price*100,
  };
}

export const formatBetMoney=cents=>Number.isFinite(cents)?dollars.format(cents/100):'Unavailable';
export const formatWin=result=>result?`Win ${formatBetMoney(result.payoutCents)} (${result.profitCents>=0?'+':''}${formatBetMoney(result.profitCents)})`:'Win estimate unavailable';

export function actualQuoteEarnings(quote){
  if(!quote||!validCents(quote.quantity)||!validCents(quote.total_cents)||!validCents(quote.cost_cents)||!Number.isSafeInteger(quote.fee_cents)||quote.fee_cents<0||quote.cost_cents+quote.fee_cents!==quote.total_cents) return null;
  return {
    contracts:quote.quantity,payoutCents:quote.quantity*100,
    profitCents:quote.quantity*100-quote.total_cents,
    totalCents:quote.total_cents,feeCents:quote.fee_cents,
  };
}

export function amountError(input,maxCents){
  const cents=parseBetAmount(input);
  if(cents==null) return 'Enter an amount above $0.00 with up to two decimal places.';
  if(!Number.isSafeInteger(maxCents)||maxCents<0) return 'Your available change is unavailable. Refresh before choosing.';
  if(cents>maxCents) return `Use up to ${formatBetMoney(maxCents)} of available change.`;
  return '';
}

export function betQuoteKey({userId,roundupId,marketId,outcome,amountCents}){
  if(!userId||!roundupId||!marketId||!['yes','no'].includes(outcome)||!validCents(amountCents)) return null;
  return JSON.stringify([userId,roundupId,marketId,outcome,amountCents]);
}

export function matchingBetQuote(record,context){
  const key=betQuoteKey(context);
  if(!key||record?.key!==key) return null;
  const data=record.data;
  if(data?.market?.id!==context.marketId||data.market.outcome!==context.outcome||usablePrice(data.market.price)==null||data.budget_cents!==context.amountCents||!actualQuoteEarnings(data.quote)||data.quote.total_cents>context.amountCents) return null;
  return data;
}
