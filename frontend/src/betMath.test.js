import {test} from 'node:test';
import assert from 'node:assert/strict';
import {
  parseBetAmount, outcomePrice, estimateEarnings, formatBetMoney, formatWin,
  actualQuoteEarnings, betQuoteKey, matchingBetQuote, amountError,
} from './betMath.js';

test('USD input is parsed as exact cents while unsafe or fractional-cent input is rejected',()=>{
  for(const [input,cents] of [['0.73',73],['$0.73',73],['.73',73],['1.',100],['1,234.56',123456],[' 12.50 ',1250]]){
    assert.equal(parseBetAmount(input),cents,input);
  }
  for(const input of ['', '0', '0.00', '-1', 'NaN', 'Infinity', '1e2', '0.731', '1,23.00', '1000000.01']){
    assert.equal(parseBetAmount(input),null,input);
  }
});

test('the requested $0.73 at $0.40 estimate rounds payout and profit independently',()=>{
  const result=estimateEarnings(73,'0.40');
  assert.equal(result.contracts,1.825);
  assert.equal(result.payoutCents,183);
  assert.equal(result.profitCents,110);
  assert.equal(result.impliedChancePercent,40);
  assert.equal(formatWin(result),'Win $1.83 (+$1.10)');
  assert.equal(formatBetMoney(73),'$0.73');
});

test('each selected outcome uses its own price and immediately changes the estimate',()=>{
  const market={prices:{yes:'0.40',no:'0.63'}};
  const yes=estimateEarnings(73,outcomePrice(market,'yes'));
  const no=estimateEarnings(73,outcomePrice(market,'no'));
  assert.equal(yes.payoutCents,183);
  assert.equal(no.payoutCents,116);
  assert.equal(no.impliedChancePercent,63);
  assert.equal(outcomePrice({prices:{yes:'0.40'}},'no'),null);
  assert.equal(outcomePrice({outcomes:[{outcome:'no',price:'0.63'}]},'no'),0.63);
});

test('missing or invalid prices and amounts never produce division errors or made-up earnings',()=>{
  for(const price of [null,undefined,'',false,0,-.2,1,Infinity,'NaN']){
    assert.equal(estimateEarnings(73,price),null,String(price));
  }
  for(const amount of [null,0,-1,NaN,Infinity,73.5]) assert.equal(estimateEarnings(amount,.4),null);
  assert.equal(outcomePrice({prices:{yes:null}},'yes'),null);
});

test('a real executable quote uses whole contracts and subtracts actual cost and fees',()=>{
  const result=actualQuoteEarnings({quantity:1,cost_cents:40,fee_cents:2,total_cents:42});
  assert.deepEqual(result,{contracts:1,payoutCents:100,profitCents:58,totalCents:42,feeCents:2});
  assert.equal(formatWin(result),'Win $1.00 (+$0.58)');
  assert.equal(actualQuoteEarnings({quantity:0,total_cents:0,fee_cents:0}),null);
  assert.equal(actualQuoteEarnings({quantity:1.5,total_cents:40,fee_cents:0}),null);
});

test('an amount over available funds is invalid before requesting an order quote',()=>{
  assert.equal(amountError('0.73',73),'');
  assert.match(amountError('0.74',73),/\$0.73/);
  assert.ok(amountError('',73));
  assert.ok(amountError('0.73',0));
});

test('quote identity includes user, purchase, market, outcome and amount to refuse stale confirmation',()=>{
  const context={userId:'one',roundupId:'roundup',marketId:'market',outcome:'yes',amountCents:73};
  const key=betQuoteKey(context);
  const data={market:{id:'market',outcome:'yes',price:'0.40'},quote:{quantity:1,cost_cents:40,total_cents:42,fee_cents:2},budget_cents:73};
  const record={key,data};
  assert.equal(matchingBetQuote(record,context),data);
  for(const change of [{userId:'two'},{roundupId:'next'},{marketId:'next'},{outcome:'no'},{amountCents:72}]){
    assert.equal(matchingBetQuote(record,{...context,...change}),null);
  }
  assert.equal(matchingBetQuote({...record,data:{...data,market:{id:'market',outcome:'no'}}},context),null);
  assert.equal(matchingBetQuote({...record,data:{...data,budget_cents:72}},context),null);
  assert.equal(betQuoteKey({...context,amountCents:null}),null);
});

test('confirmation refuses malformed executable quotes or missing live prices',()=>{
  const context={userId:'one',roundupId:'roundup',marketId:'market',outcome:'yes',amountCents:73};
  const data={market:{id:'market',outcome:'yes',price:'0.40'},quote:{quantity:1,cost_cents:40,total_cents:42,fee_cents:2},budget_cents:73};
  const key=betQuoteKey(context);
  for(const price of [undefined,null,'',0,1,'NaN']){
    assert.equal(matchingBetQuote({key,data:{...data,market:{...data.market,price}}},context),null);
  }
  assert.equal(matchingBetQuote({key,data:{...data,quote:{...data.quote,total_cents:80,cost_cents:78}}},context),null);
  assert.equal(actualQuoteEarnings({...data.quote,cost_cents:41}),null);
});
