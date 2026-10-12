import hashlib,hmac,json,os,time
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_FLOOR,ROUND_CEILING
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2]/'.env')
from fastapi import FastAPI,HTTPException,Request,BackgroundTasks,Query,Response
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,field_validator
from sqlalchemy import select,func,text
from sqlalchemy.orm import Session
from .database import User,Pot,Purchase,Roundup,Position,PlaidItem,SandboxOrder,build_engine,timestamp,uid
from .money import parse_cents,roundup_cents,order_quote,fee_cents,bank_amount
from .purchase_metadata import is_purchase_entry,plaid_purchase_name,is_demo_purchase
from .providers import Gemini,Plaid,ProviderError,ProviderRejected
from .scoring import TOPICS,WEIGHTS,rank_markets,topic_for
from .market_catalog import event_catalog
from .access import register_access
from .context_reading import ContextReading
from . import squad_models,swarm_models,xrpl_models
from .squads import register_squads
from .news import register_news
from .swarm import register_swarm,swarm_config
from .swarm_connections import register_swarm_connections
from .xrpl_service import register_xrpl,xrpl_configured

class Onboarding(BaseModel):
    name:str=Field(min_length=1,max_length=50)
    interests:list[str]=Field(default_factory=list,max_length=6)
    @field_validator('name')
    @classmethod
    def name_not_blank(cls,v):
        if not v.strip(): raise ValueError('Enter your name.')
        return v.strip()
    @field_validator('interests')
    @classmethod
    def valid_topics(cls,v):
        if any(t not in TOPICS for t in v): raise ValueError('Choose a supported interest.')
        return list(dict.fromkeys(v))
class Settings(BaseModel):
    interests:list[str]|None=None
    paused:bool|None=None
    @field_validator('interests')
    @classmethod
    def valid_topics(cls,v):
        if v is not None and any(t not in TOPICS for t in v): raise ValueError('Choose a supported interest.')
        return v
class PurchaseInput(BaseModel):
    user_id:str
    amount:str|float|int
    merchant:str=Field(min_length=1,max_length=160)
    category:str=Field(default='',max_length=80)
    source:Literal['manual','shortcut','plaid']='manual'
    source_id:str|None=Field(default=None,max_length=200)
    @field_validator('merchant')
    @classmethod
    def merchant_not_blank(cls,v):
        if not v.strip(): raise ValueError('Enter a merchant.')
        return v.strip()
class Allocation(BaseModel):
    user_id:str
    destination:Literal['savings','market','rollover']
    market_id:str|None=None
    outcome:Literal['yes','no']='yes'
    max_price:str|None=None
    max_quantity:int|None=Field(default=None,ge=1,le=100000)
    max_total_cents:int|None=Field(default=None,ge=1,le=100000)
    amount_cents:int|None=Field(default=None,ge=1)
class UserInput(BaseModel): user_id:str


def user_json(u): return {'id':u.id,'name':u.name,'interests':u.interests,'paused':u.paused}
def purchase_json(p,r):
    return {'id':p.id,'roundup_id':r.id,'amount_cents':p.amount_cents,'merchant':p.merchant,'category':p.category,'source':p.source,'created_at':p.created_at,'roundup_cents':r.amount_cents,'allocation':r.allocation,'market_title':r.market_title,'notice':p.notice,'is_purchase':is_purchase_entry(p.merchant,p.category,p.source)}
def week_start():
    now=datetime.now(ZoneInfo('America/Los_Angeles'))
    return (now-timedelta(days=now.weekday())).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat()

def create_app(database_url=None,feed=None,plaid=None,mode=None):
    app=FastAPI(title='Spare Change Predictions',version='1.0.0')
    access=register_access(app)
    engine=build_engine(database_url or os.getenv('DATABASE_URL','sqlite:///./spare_change.db'))
    mode=mode or os.getenv('TRADING_MODE','paper')
    feed=feed or Gemini(Gemini.SANDBOX if mode=='sandbox' else None); plaid=plaid or Plaid()
    reading=ContextReading()
    app.state.engine=engine; app.state.feed=feed; app.state.mode=mode; app.state.reading=reading
    @contextmanager
    def db(write=False):
        with Session(engine) as s:
            try:
                if write: s.execute(text('BEGIN IMMEDIATE'))
                yield s
                if write: s.commit()
            except Exception:
                s.rollback(); raise
    def get_user(s,id):
        u=s.get(User,id)
        if not u: raise HTTPException(404,'User not found. Start with onboarding.')
        return u
    def get_roundup(s,id,user_id):
        pair=s.execute(select(Purchase,Roundup).join(Roundup,Roundup.purchase_id==Purchase.id).where(Roundup.id==id,Purchase.user_id==user_id)).first()
        if not pair: raise HTTPException(404,'Round-up not found.')
        if not is_purchase_entry(pair[0].merchant,pair[0].category,pair[0].source): raise HTTPException(409,'This Plaid entry is a financial charge or transfer, not a purchase.')
        return pair
    def weekly_spent(s,u):
        spent=s.scalar(select(func.coalesce(func.sum(Position.cost_cents+Position.fee_cents),0)).where(Position.user_id==u,Position.created_at>=week_start()))
        reserved=s.scalar(select(func.coalesce(func.sum(SandboxOrder.reserved_cents),0)).where(SandboxOrder.user_id==u,SandboxOrder.created_at>=week_start(),SandboxOrder.status.in_(['submitting','unknown','open'])))
        return spent+reserved
    def pending_roundups(s,user_id):
        rows=s.execute(select(Purchase,Roundup).join(Roundup,Purchase.id==Roundup.purchase_id).where(Purchase.user_id==user_id,Roundup.allocation=='pending')).all()
        return [r for p,r in rows if is_purchase_entry(p.merchant,p.category,p.source)]
    def market_budget(available,amount_cents=None):
        budget=available
        if amount_cents is not None:
            if amount_cents>available: raise HTTPException(409,'The chosen amount exceeds your accumulated change balance.')
            budget=amount_cents
        return budget
    def collect_change(s,user_id,anchor):
        rows=pending_roundups(s,user_id)
        collected=sum(row.amount_cents for row in rows)
        for row in rows:
            if row.id!=anchor.id:
                row.allocation='rollover';row.allocated_at=timestamp()
        return collected
    def record(s,payload):
        get_user(s,payload.user_id)
        try: amount=parse_cents(payload.amount)
        except ValueError as exc: raise HTTPException(422,str(exc))
        if payload.source_id:
            existing=s.scalar(select(Purchase).where(Purchase.user_id==payload.user_id,Purchase.source==payload.source,Purchase.source_id==payload.source_id))
            if existing:
                if existing.amount_cents!=amount or existing.merchant!=payload.merchant: raise HTTPException(409,'This purchase ID already has different details.')
                return existing,s.scalar(select(Roundup).where(Roundup.purchase_id==existing.id))
        p=Purchase(user_id=payload.user_id,amount_cents=amount,merchant=payload.merchant,category=payload.category,source=payload.source,source_id=payload.source_id)
        s.add(p); s.flush(); change=roundup_cents(amount)
        r=Roundup(purchase_id=p.id,amount_cents=change,allocation='pending' if change else 'no_change'); s.add(r); s.flush()
        return p,r
    @app.exception_handler(ProviderError)
    def provider_error(request,exc): return JSONResponse(status_code=503,content={'detail':str(exc)})
    @app.get('/health')
    def health(): return {'status':'ok','trading_mode':mode,'plaid_configured':bool(os.getenv('PLAID_CLIENT_ID') and os.getenv('PLAID_SECRET')),'gemini_configured':bool(os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_API_SECRET')),'context_configured':bool(os.getenv('CONTEXT_DEV_API_KEY')),'anthropic_configured':bool(os.getenv('ANTHROPIC_API_KEY')),'swarm_provider':swarm_config()['provider'],'swarm_configured':swarm_config()['configured'],'xrpl_configured':xrpl_configured()}
    @app.post('/users',status_code=201)
    def create_user(payload:Onboarding,background_tasks:BackgroundTasks,response:Response):
        with db(True) as s:
            u=User(**payload.model_dump()); s.add(u); s.flush(); s.add(Pot(user_id=u.id)); result=user_json(u)
        if xrpl_configured(): background_tasks.add_task(app.state.xrpl_service.create_wallet_in_background,result['id'])
        access.set_profile(response,result['id'])
        return result
    @app.get('/users/{id}')
    def read_user(id:str):
        with db() as s: return user_json(get_user(s,id))
    @app.patch('/users/{id}')
    def update_user(id:str,payload:Settings):
        with db(True) as s:
            u=get_user(s,id)
            for k,v in payload.model_dump(exclude_none=True).items(): setattr(u,k,v)
            return user_json(u)
    @app.post('/purchases',status_code=201)
    def add_purchase(payload:PurchaseInput):
        with db(True) as s: return purchase_json(*record(s,payload))
    @app.get('/transactions')
    def transactions(user_id:str):
        with db() as s:
            get_user(s,user_id)
            rows=s.execute(select(Purchase,Roundup).join(Roundup,Roundup.purchase_id==Purchase.id).where(Purchase.user_id==user_id).order_by(Purchase.created_at.desc())).all()
            return [purchase_json(p,r) for p,r in rows]
    @app.get('/suggestions')
    def suggestions(user_id:str,roundup_id:str|None=None):
        with db() as s:
            u=get_user(s,user_id); pot=s.get(Pot,user_id)
            purchase=None; change=0
            if roundup_id:
                p,r=get_roundup(s,roundup_id,user_id); purchase=purchase_json(p,r)
                if r.allocation=='pending': change=r.amount_cents
            budget=pot.rollover_cents+sum(row.amount_cents for row in pending_roundups(s,user_id))
            reason='paused' if u.paused else ('no_change' if budget==0 else None)
            history=[{'amount_cents':p.amount_cents,'merchant':p.merchant,'category':p.category} for p in s.scalars(select(Purchase).where(Purchase.user_id==user_id,Purchase.notice.is_(None))).all() if is_purchase_entry(p.merchant,p.category,p.source)]
            past=[topic_for(p.category) for p in s.scalars(select(Position).where(Position.user_id==user_id)).all()]
            interests=u.interests
        rows=[] if reason else feed.markets()
        ranked=rank_markets(rows,interests,history,past,budget) if rows else []
        grouped={event['id']:event for event in event_catalog(rows)}
        events=[]; seen_events=set()
        for market in ranked:
            ticker=market['event_ticker']
            if ticker in grouped and ticker not in seen_events:
                events.append({**grouped[ticker],'why':market['why']}); seen_events.add(ticker)
        return {'markets':ranked,'events':events,'reason':reason or ('no_affordable_markets' if not ranked else None),'budget_cents':budget,'rollover_cents':pot.rollover_cents,'purchase':purchase,'weights':WEIGHTS,'fetched_at':timestamp(),'mode':mode}
    @app.get('/markets/events')
    def market_events(query:str|None=None):
        return {'events':event_catalog(feed.markets(),query),'source':'gemini'}
    @app.get('/markets/context')
    def market_context(user_id:str,market_id:str,outcome:Literal['yes','no']='yes'):
        with db() as s: get_user(s,user_id)
        market=next((m for m in feed.markets() if m['id']==market_id and m['outcome']==outcome),None)
        if not market: raise HTTPException(404,'This contract is no longer in the open market feed.')
        return reading.materials(market.get('title',''),market.get('label',''))
    @app.get('/markets/quote')
    def market_quote(user_id:str,roundup_id:str,market_id:str,outcome:Literal['yes','no']='yes',amount_cents:int|None=Query(default=None,ge=1)):
        with db() as s:
            u=get_user(s,user_id); p,r=get_roundup(s,roundup_id,user_id)
            if r.allocation!='pending': raise HTTPException(409,'This round-up already has a destination.')
            if u.paused: raise HTTPException(409,'Market picks are paused in your preferences.')
            available=sum(row.amount_cents for row in pending_roundups(s,user_id))+s.get(Pot,user_id).rollover_cents
            budget=market_budget(available,amount_cents)
        market=feed.market(market_id,outcome)
        if not market or market.get('id')!=market_id or market.get('outcome')!=outcome or market.get('status')!='active' or market.get('market_state') not in (None,'open') or market.get('resolution'): raise HTTPException(404,'This market is no longer open.')
        try:
            closes=datetime.fromisoformat(market['closes_at'].replace('Z','+00:00'))
            if closes.tzinfo is None or closes<=datetime.now(timezone.utc): raise ValueError()
            price=Decimal(str(market['price']))
            if not price.is_finite() or not 0<price<1: raise ValueError()
        except (ValueError,KeyError,TypeError,ArithmeticError): raise HTTPException(409,'A current buy quote is unavailable.')
        quote=order_quote(budget,price,market.get('quantity_minimum') or '1',market.get('quantity_increment') or '1')
        if not quote or not quote['quantity']: raise HTTPException(409,'This quote exceeds your accumulated change balance.')
        return {'market':market,'quote':quote,'budget_cents':budget,'available_cents':available,'mode':mode}
    def position_from(s,u,r,m,q,entry,trade_mode):
        pos=Position(user_id=u,roundup_id=r.id,market_id=m['id'],event_ticker=m['event_ticker'],title=m['title']+' · '+m.get('label',''),category=m['category'],outcome=m['outcome'],quantity=q['quantity'],entry_price=str(entry),cost_cents=q['cost_cents'],fee_cents=q['fee_cents'],mode=trade_mode)
        s.add(pos); r.allocation='market'; r.market_title=pos.title; r.allocated_at=timestamp(); return pos
    def finish_order(order_id,response):
        with db(True) as s:
            o=s.get(SandboxOrder,order_id)
            if o.status in ['filled','cancelled','rejected']: return {'status':o.status,'order_id':o.id}
            if response.get('orderId') is not None: o.exchange_id=str(response['orderId'])
            filled=Decimal(str(response.get('filledQuantity') or '0'))
            status=response.get('status'); pot=s.get(Pot,o.user_id); r=s.get(Roundup,o.roundup_id)
            if status=='cancelled' and filled==0:
                o.status='cancelled'; pot.rollover_cents+=o.reserved_cents; r.allocation='rollover'; r.market_title=None
                return {'status':'cancelled','order_id':o.id,'message':'No fill. Your change stayed in the pot.'}
            if status=='filled' and filled==o.quote['quantity'] and response.get('avgExecutionPrice') is not None:
                price=Decimal(response['avgExecutionPrice'])
                cost=int((price*filled*100).to_integral_value(rounding=ROUND_CEILING)); fee=fee_cents(filled,price)
                if cost+fee>o.reserved_cents:
                    o.status='unknown'; o.message='Reported fill exceeds reservation. Check the sandbox account.'
                    return {'status':'unknown','order_id':o.id,'message':o.message}
                q={**o.quote,'cost_cents':cost,'fee_cents':fee}
                position_from(s,o.user_id,r,o.market,q,price,'sandbox'); pot.rollover_cents+=o.reserved_cents-cost-fee; o.status='filled'
                return {'status':'filled','order_id':o.id,'quantity':int(filled),'fee_cents':fee}
            o.status='open' if status=='open' else 'unknown'; o.message='Waiting for a verified full fill or cancellation.'
            return {'status':o.status,'order_id':o.id,'message':o.message}
    @app.post('/roundups/{id}/allocate')
    def allocate(id:str,payload:Allocation):
        if payload.destination=='market' and mode not in ['paper','sandbox']: raise HTTPException(409,'Use TRADING_MODE=paper or sandbox. Real-money trading is not enabled in this MVP.')
        with db(True) as s:
            u=get_user(s,payload.user_id); p,r=get_roundup(s,id,u.id); pot=s.get(Pot,u.id)
            if r.allocation!='pending': raise HTTPException(409,'This round-up has already been handled.')
            if payload.destination=='savings':
                pot.savings_cents+=r.amount_cents; r.allocation='savings'; r.allocated_at=timestamp()
                return {'status':'saved','amount_cents':r.amount_cents}
            if payload.destination=='rollover':
                pot.rollover_cents+=r.amount_cents; r.allocation='rollover'; r.allocated_at=timestamp()
                return {'status':'rollover','amount_cents':r.amount_cents,'message':'Change held in your pot for a future market pick.'}
            if u.paused: raise HTTPException(409,'Market picks are paused. You can still save your change.')
            budget=market_budget(pot.rollover_cents+sum(row.amount_cents for row in pending_roundups(s,u.id)),payload.amount_cents)
            if not payload.market_id: raise HTTPException(422,'Choose a market.')
            m=feed.market(payload.market_id,payload.outcome)
            if m.get('status')!='active' or m.get('market_state') not in [None,'open'] or not m.get('price'):
                raise HTTPException(409,'This market is not currently open for this outcome.')
            if not m.get('closes_at') or datetime.fromisoformat(m['closes_at'].replace('Z','+00:00'))<=datetime.now(timezone.utc): raise HTTPException(409,'This market has closed.')
            price=Decimal(m['price'])
            try:
                if payload.max_price is not None and price>Decimal(payload.max_price): raise HTTPException(409,'The price increased. Refresh the choices before confirming.')
                if payload.max_total_cents is not None: budget=min(budget,payload.max_total_cents)
                q=order_quote(budget,price,m.get('quantity_minimum') or '1',m.get('quantity_increment') or '1',payload.max_quantity)
            except (ValueError,ArithmeticError): raise HTTPException(409,'The contract price or quantity is invalid.')
            if q['quantity']==0: raise HTTPException(409,'Your change cannot cover one whole contract and its fee. Save it or wait for more change.')
            if mode=='paper':
                pot.rollover_cents+=collect_change(s,u.id,r)-q['total_cents']; position_from(s,u.id,r,m,q,price,'paper')
                return {'status':'paper','quantity':q['quantity'],'fee_cents':q['fee_cents'],'leftover_cents':pot.rollover_cents}
            # Reserve locally before touching the exchange. FOK avoids a resting partial order.
            if not os.getenv('GEMINI_API_KEY') or not os.getenv('GEMINI_API_SECRET'): raise ProviderError('Set GEMINI_API_KEY and GEMINI_API_SECRET from a Gemini sandbox account in .env.')
            feed.ensure_trading_ready()
            o=SandboxOrder(user_id=u.id,roundup_id=r.id,market=m,quote=q,reserved_cents=q['total_cents']); s.add(o); s.flush(); order_id=o.id
            pot.rollover_cents+=collect_change(s,u.id,r)-q['total_cents']; r.allocation='order_pending'; r.allocated_at=timestamp(); r.market_title=m['title']
        try: response=feed.place_order(m,q['quantity'])
        except ProviderRejected as exc:
            with db(True) as s:
                o=s.get(SandboxOrder,order_id); o.status='rejected'; o.message=str(exc)
                s.get(Pot,o.user_id).rollover_cents+=o.reserved_cents
                s.get(Roundup,o.roundup_id).allocation='rollover'
            return {'status':'rejected','order_id':order_id,'message':'Order rejected. Your change stayed in the pot. '+str(exc)}
        except ProviderError as exc:
            # A transport failure might have happened after Gemini accepted the order. Never retry automatically.
            with db(True) as s:
                o=s.get(SandboxOrder,order_id); o.status='unknown'; o.message=str(exc)
            return {'status':'unknown','order_id':order_id,'message':'Order outcome is uncertain. Check your Gemini sandbox account before retrying. '+str(exc)}
        return finish_order(order_id,response)
    @app.post('/sandbox/orders/{id}/reconcile')
    def reconcile(id:str,payload:UserInput):
        with db() as s:
            get_user(s,payload.user_id); o=s.get(SandboxOrder,id)
            if not o or o.user_id!=payload.user_id: raise HTTPException(404,'Order not found.')
            if not o.exchange_id: raise HTTPException(409,'No exchange order ID was received. Check Gemini sandbox order history manually; this reservation will not be retried automatically.')
            response=feed.lookup_order(o.market['id'],o.exchange_id)
        return finish_order(id,response)
    @app.get('/dashboard')
    def dashboard(user_id:str):
        # Fetch outside the write transaction; verify resolutions before crediting once.
        with db() as s:
            get_user(s,user_id); events=set(s.scalars(select(Position.event_ticker).where(Position.user_id==user_id,Position.status=='open')).all())
        snapshots={}; errors=[]
        for event in events:
            try:
                for m in feed.event(event): snapshots[(m['id'],m['outcome'])]=m
            except ProviderError as exc: errors.append(str(exc))
        with db(True) as s:
            u=get_user(s,user_id); pot=s.get(Pot,user_id); positions=s.scalars(select(Position).where(Position.user_id==user_id).order_by(Position.created_at.desc())).all(); current=0; complete=True; serialized=[]
            for p in positions:
                m=snapshots.get((p.market_id,p.outcome)); value=None
                if p.status=='open' and m and m.get('resolution') in ['yes','no']:
                    p.payout_cents=p.quantity*100 if m['resolution']==p.outcome else 0; p.status='won' if p.payout_cents else 'lost'; pot.rollover_cents+=p.payout_cents
                if p.status=='open' and m and m.get('status')=='invalid':
                    p.payout_cents=p.cost_cents; p.status='refunded'; pot.rollover_cents+=p.payout_cents
                if p.status=='open':
                    try:
                        bid=Decimal(str(m['sell_price'])) if m and m.get('sell_price') is not None else None
                        if bid is not None and 0<=bid<=1: value=int((bid*p.quantity*100).to_integral_value(rounding=ROUND_FLOOR)); current+=value
                        else: complete=False
                    except ArithmeticError: complete=False
                serialized.append({'id':p.id,'market_id':p.market_id,'title':p.title,'category':p.category,'outcome':p.outcome,'quantity':p.quantity,'entry_price':p.entry_price,'cost_cents':p.cost_cents,'fee_cents':p.fee_cents,'status':p.status,'current_value_cents':value,'payout_cents':p.payout_cents,'mode':p.mode})
            s.flush(); rows=s.execute(select(Purchase,Roundup).join(Roundup,Roundup.purchase_id==Purchase.id).where(Purchase.user_id==user_id)).all()
            baseline=sum(r.amount_cents for p,r in rows if r.allocation in ['pending','savings','market','order_pending','rollover'] and (is_purchase_entry(p.merchant,p.category,p.source) or r.allocation!='pending'))
            orders=s.scalars(select(SandboxOrder).where(SandboxOrder.user_id==user_id,SandboxOrder.status.in_(['unknown','open','submitting']))).all()
            pending_orders=[{'id':o.id,'exchange_id':o.exchange_id,'status':o.status,'title':o.market['title'],'reserved_cents':o.reserved_cents,'message':o.message} for o in orders]
            pending=sum(r.amount_cents for r in pending_roundups(s,user_id));available=pot.rollover_cents+pending
            total=pot.savings_cents+available+current if complete and not orders else None
            return {'user':user_json(u),'mode':mode,'pot_cents':pot.savings_cents+available,'savings_cents':pot.savings_cents,'rollover_cents':pot.rollover_cents,'available_cents':available,'market_value_cents':current if complete else None,'total_value_cents':total,'savings_comparison_cents':baseline,'difference_cents':total-baseline if total is not None else None,'pending_cents':pending,'weekly_spent_cents':weekly_spent(s,user_id),'positions':serialized,'wins':sum(p.status=='won' for p in positions),'losses':sum(p.status=='lost' for p in positions),'pending_orders':pending_orders,'price_errors':errors,'valued_at':timestamp()}
    def ingest(s,item,data,demo_batch=None):
        count=0
        for t in data['added']+data['modified']:
            if demo_batch and not is_demo_purchase(t,demo_batch): continue
            tid=t['transaction_id']; existing=s.scalar(select(Purchase).where(Purchase.user_id==item.user_id,Purchase.source=='plaid',Purchase.source_id==tid))
            eligible=not t.get('pending') and t.get('iso_currency_code')=='USD'
            if eligible:
                try: amount=bank_amount(t.get('amount'))
                except ValueError: raise ProviderError('Plaid returned an invalid USD transaction amount. Try syncing again.') from None
                eligible=Decimal(amount)>0 and is_purchase_entry(plaid_purchase_name(t),(t.get('personal_finance_category') or {}).get('primary',''))
            if not eligible:
                if existing:
                    r=s.scalar(select(Roundup).where(Roundup.purchase_id==existing.id))
                    existing.notice='Plaid changed this entry to pending, non-USD, non-positive, or a financial charge/transfer. Review any prior allocation.'
                    if r.allocation in ['pending','no_change']: r.allocation='removed'
                continue
            payload=PurchaseInput(user_id=item.user_id,amount=amount,merchant=plaid_purchase_name(t),category=(t.get('personal_finance_category') or {}).get('primary',''),source='plaid',source_id=tid)
            if existing:
                r=s.scalar(select(Roundup).where(Roundup.purchase_id==existing.id)); new_amount=parse_cents(payload.amount)
                if r.allocation in ['pending','no_change','removed']:
                    existing.amount_cents=new_amount; existing.merchant=payload.merchant; existing.category=payload.category; existing.notice=None; r.amount_cents=roundup_cents(new_amount); r.allocation='pending' if r.amount_cents else 'no_change'
                elif existing.amount_cents!=new_amount: existing.notice='Plaid changed this purchase after allocation. Review it manually.'
            else: record(s,payload); count+=1
        for t in data['removed']:
            p=s.scalar(select(Purchase).where(Purchase.user_id==item.user_id,Purchase.source=='plaid',Purchase.source_id==t['transaction_id']))
            if p:
                r=s.scalar(select(Roundup).where(Roundup.purchase_id==p.id)); p.notice='Removed by Plaid.'
                if r.allocation in ['pending','no_change']: r.allocation='removed'
        item.cursor=data['cursor']; return count
    @app.post('/demo/seed')
    def demo(payload:UserInput):
        with db() as s:
            get_user(s,payload.user_id); item=s.scalar(select(PlaidItem).where(PlaidItem.user_id==payload.user_id))
            access=item.access_token if item else None; cursor=item.cursor if item else ''
        if not access:
            connected=plaid.connect(os.getenv('PLAID_WEBHOOK_URL')); access=connected['access_token']; initial=plaid.sync(access); cursor=initial['cursor']
            with db(True) as s:
                existing=s.scalar(select(PlaidItem).where(PlaidItem.user_id==payload.user_id))
                if existing: raise HTTPException(409,'A Plaid connection was created concurrently. Retry the demo.')
                s.add(PlaidItem(item_id=connected['item_id'],user_id=payload.user_id,access_token=access,cursor=cursor))
        batch=uid()
        purchases=[{'amount':4.63,'merchant':'Starbucks'},{'amount':18.21,'merchant':'Ticketmaster'},{'amount':32.56,'merchant':'Shell'}]
        plaid.create_purchases(access,[{**p,'description':f'Spare demo {batch}: {p["merchant"]}'} for p in purchases])
        count=0
        for _ in range(8):
            data=plaid.sync(access,cursor)
            with db(True) as s:
                item=s.scalar(select(PlaidItem).where(PlaidItem.user_id==payload.user_id))
                if item.cursor!=cursor: raise HTTPException(409,'Plaid was synced concurrently. Your purchases are in the feed; refresh it.')
                count+=ingest(s,item,data,batch); cursor=data['cursor']
            if count>=3: break
            time.sleep(1)
        return {'created':count,'status':'synced' if count>=3 else 'processing','message':'Purchases were created in Plaid sandbox. '+('Open the feed to allocate your change.' if count>=3 else 'Plaid is still processing; use Sync purchases in a moment.')}
    @app.post('/plaid/sync')
    def sync(payload:UserInput):
        with db() as s:
            get_user(s,payload.user_id); item=s.scalar(select(PlaidItem).where(PlaidItem.user_id==payload.user_id))
            if not item: raise HTTPException(404,'Run the Plaid demo to connect the sandbox first.')
            access=item.access_token; cursor=item.cursor; item_id=item.item_id
        data=plaid.sync(access,cursor)
        with db(True) as s:
            item=s.get(PlaidItem,item_id)
            if item.cursor!=cursor: raise HTTPException(409,'Another sync finished first. Refresh the feed.')
            return {'created':ingest(s,item,data)}
    @app.post('/webhooks/plaid')
    async def webhook(request:Request):
        import jwt
        body=await request.body(); verification=request.headers.get('Plaid-Verification')
        if not verification: raise HTTPException(401,'Missing Plaid webhook signature.')
        try:
            header=jwt.get_unverified_header(verification)
            if header.get('alg')!='ES256': raise ValueError('Unexpected signature algorithm')
            jwk=plaid.call('/webhook_verification_key/get',{'key_id':header['kid']})['key']
            claims=jwt.decode(verification,jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk)),algorithms=['ES256'],options={'require':['iat'],'verify_aud':False})
            if abs(time.time()-claims['iat'])>300 or not hmac.compare_digest(hashlib.sha256(body).hexdigest(),claims.get('request_body_sha256','')): raise ValueError('Invalid signature age or body hash')
        except (ValueError,KeyError,jwt.PyJWTError): raise HTTPException(401,'Invalid Plaid webhook signature.')
        data=json.loads(body)
        if data.get('webhook_type')!='TRANSACTIONS' or data.get('webhook_code')!='SYNC_UPDATES_AVAILABLE': return {'status':'ignored'}
        if data.get('environment')!='sandbox': raise HTTPException(400,'Only sandbox webhooks are supported.')
        with db() as s:
            item=s.get(PlaidItem,data.get('item_id'))
            if not item: return {'status':'ignored'}
            user_id=item.user_id
        return sync(UserInput(user_id=user_id))
    register_squads(app,engine,feed)
    register_swarm(app,engine,feed,reading)
    register_swarm_connections(app,engine)
    register_news(app,engine,feed,reading)
    register_xrpl(app,engine,feed)
    static=Path(__file__).resolve().parents[2]/'frontend'/'dist'
    if static.exists():
        app.mount('/assets',StaticFiles(directory=static/'assets'),name='assets')
        @app.get('/{path:path}',include_in_schema=False)
        def frontend(path:str):
            candidate=(static/path).resolve()
            if candidate.is_relative_to(static.resolve()) and candidate.is_file(): return FileResponse(candidate)
            return FileResponse(static/'index.html')
    return app

app=create_app()
