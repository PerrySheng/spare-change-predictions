"""Short public-source reading, ordered by actual local category history."""
from collections import defaultdict
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from .database import User, Position
from .squad_models import SquadLeg
from .scoring import TOPICS, topic_for


def history_weights(interests, history):
    groups=defaultdict(list)
    for row in history:
        groups[topic_for(row['category'])].append(row)
    weights={}
    for topic in dict.fromkeys([*TOPICS,*groups.keys()]):
        rows=groups[topic]
        resolved=[r for r in rows if r['status'] in ('won','lost')]
        edge=sum((1 if r['status']=='won' else 0)-float(r['entry_price']) for r in resolved)/len(resolved) if resolved else None
        # A positive observed edge has a small, sample-weighted boost. Losses never
        # raise a category's weight; no sizing or trading advice is produced here.
        boost=5*max(edge or 0,0)*min(len(resolved)/5,1)
        weights[topic]={'weight':round((2 if topic in interests else 0)+min(len(rows),20)+boost,4),
                       'picks':len(rows),'resolved':len(resolved),'edge_score':round(edge,6) if edge is not None else None}
    return weights


def unique_markets(rows):
    grouped={}
    now=datetime.now(timezone.utc)
    for row in rows:
        try:
            closes=datetime.fromisoformat(row['closes_at'].replace('Z','+00:00'))
            if closes.tzinfo is None or closes<=now: continue
        except (KeyError,ValueError,TypeError): continue
        if row.get('status')!='active' or row.get('market_state') not in (None,'open') or row.get('resolution'): continue
        m=grouped.setdefault(row['id'],{k:row.get(k) for k in ('id','event_ticker','title','label','category','closes_at','terms_url','volume')})
        m.setdefault('prices',{})[row['outcome']]=row.get('price')
        m['topic']=topic_for(row['category'])
    return list(grouped.values())


def order_markets(rows,weights):
    markets=unique_markets(rows)
    for m in markets: m['topic_history']=weights.get(m['topic'],{'weight':0,'picks':0,'resolved':0,'edge_score':None})
    return sorted(markets,key=lambda m:(-m['topic_history']['weight'],m['closes_at'],m['id']))


def related_markets(rows,market):
    topic=topic_for(market['category'])
    result=[m for m in unique_markets(rows) if m['topic']==topic]
    result.sort(key=lambda m:(m['id']!=market['id'],m['closes_at'],m['id']))
    return result[:4]


def register_news(app,engine,feed,reading):
    def weights_for(user_id):
        with Session(engine) as s:
            u=s.get(User,user_id)
            if not u: raise HTTPException(404,'User not found. Start with onboarding.')
            history=[{'category':p.category,'status':p.status,'entry_price':p.entry_price} for p in s.scalars(select(Position).where(Position.user_id==user_id))]
            history.extend({'category':p.category,'status':p.status,'entry_price':p.entry_price} for p in s.scalars(select(SquadLeg).where(SquadLeg.user_id==user_id,SquadLeg.active.is_(True))))
            return history_weights(u.interests,history)
    @app.get('/news/markets')
    def news_markets(user_id:str,market_id:str|None=None):
        weights=weights_for(user_id)
        ordered=order_markets(feed.markets(),weights)
        markets=ordered[:40]
        if market_id and not any(m['id']==market_id for m in markets):
            selected=next((m for m in ordered if m['id']==market_id),None)
            if selected: markets.insert(0,selected)
        return {'markets':markets,'topics':weights,
                'method':'Interests plus actual category picks and sample-weighted positive edge. Losses never increase the edge boost.'}
    @app.get('/news/articles')
    def news_articles(user_id:str,market_id:str):
        weights=weights_for(user_id)
        rows=feed.markets()
        market=next((m for m in unique_markets(rows) if m['id']==market_id),None)
        if not market: raise HTTPException(404,'This market is no longer open.')
        from .swarm import cached_sources,cache_sources
        sources=cached_sources(engine,market_id)
        if sources:
            result={'provider':'Shared research cache','sources':sources[:5],'cached':True,'partial':False}
        else:
            result=reading.materials(market['title'],market.get('label') or '')
            cache_sources(engine,market_id,result['sources'],'Context.dev')
        return {**result,'market':market,'related_markets':related_markets(rows,market),'topics':weights,
                'matching':'Related markets share this market’s Gemini topic. Source links are reading material, not verified predictions.'}
