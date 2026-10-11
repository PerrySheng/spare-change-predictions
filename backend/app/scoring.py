"""Deterministic ranking: no outcome or loss is ever an input."""
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
from math import log1p
from .money import order_quote
TOPICS=['sports','crypto','politics','weather','entertainment','economy']
WEIGHTS={'interest':40.,'spending':25.,'past_picks':12.,'affordability':8.,'closes_soon':10.,'liquidity':5.}
CATEGORY_TOPICS={'TRAVEL':['weather'],'ENTERTAINMENT':['entertainment','sports'],'FOOD_AND_DRINK':['economy'],'TRANSPORTATION':['economy'],'GENERAL_MERCHANDISE':['economy'],'GAS':['economy'],'TRANSFER_OUT':['crypto']}
MERCHANT_TOPICS={'airlines':['weather'],'airbnb':['weather'],'hotel':['weather'],'starbucks':['economy'],'shell':['economy'],'chevron':['economy'],'netflix':['entertainment'],'ticketmaster':['sports','entertainment'],'coinbase':['crypto'],'gemini':['crypto']}
def topic_for(category):
    c=category.lower()
    for topic in TOPICS:
        if topic in c: return topic
    if any(x in c for x in ['economic','finance','commodit','energy']): return 'economy'
    return c
def spending_topics(transactions):
    amounts=Counter()
    for t in transactions:
        topics=set(CATEGORY_TOPICS.get(str(t.get('category','')).upper(),[]))
        for merchant,matched in MERCHANT_TOPICS.items():
            if merchant in t.get('merchant','').lower(): topics.update(matched)
        for topic in topics: amounts[topic]+=t['amount_cents']
    return amounts
def rank_markets(markets,interests,transactions,past_topics,budget,now=None):
    now=now or datetime.now(timezone.utc); spend=spending_topics(transactions); total_spend=sum(t['amount_cents'] for t in transactions) or 1
    past=Counter(past_topics); past_total=sum(past.values()) or 1
    max_volume=max([float(m.get('volume') or 0) for m in markets]+[1.]); results=[]
    for m in markets:
        try:
            close=datetime.fromisoformat(m['closes_at'].replace('Z','+00:00')); days=(close-now).total_seconds()/86400
            if days<=0: continue
            quote=order_quote(budget,Decimal(m['price']),Decimal(m.get('quantity_minimum') or '1'),Decimal(m.get('quantity_increment') or '1'))
            if not quote['quantity']: continue
            topic=m.get('topic') or topic_for(m['category']); volume=max(float(m.get('volume') or 0),0)
        except (ValueError,TypeError,KeyError): continue
        f={'interest':WEIGHTS['interest']*int(topic in interests),'spending':WEIGHTS['spending']*min(spend[topic]/total_spend,1),'past_picks':WEIGHTS['past_picks']*past[topic]/past_total,'affordability':WEIGHTS['affordability']*(1-float(m['price'])*100/max(budget,1)),'closes_soon':WEIGHTS['closes_soon']*max(0,1-days/14),'liquidity':WEIGHTS['liquidity']*log1p(volume)/log1p(max_volume)}
        f={k:round(v,4) for k,v in f.items()}
        if f['interest']>0: why=f'Matches your interest in {topic}.'
        elif f['spending']>0: why=f'Your spending connects to {topic} ({round(100*min(spend[topic]/total_spend,1))}% of purchases).'
        elif f['past_picks']>0: why=f'You have chosen {topic} markets {past[topic]} time(s).'
        elif f['closes_soon']>0: why=f'Closes in {max(1,round(days*24))} hours and fits your available change.'
        else: why=f'Fits your available change; ${volume:,.2f} in reported event volume.'
        results.append({**m,'topic':topic,'factors':f,'score':round(sum(f.values()),4),'why':why,'quote':quote})
    results.sort(key=lambda m:(-m['score'],m['id'])); seen=set(); unique=[]
    for m in results:
        if m['event_ticker'] not in seen: unique.append(m); seen.add(m['event_ticker'])
        if len(unique)==3: break
    return unique
