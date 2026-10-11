from datetime import datetime,timedelta,timezone
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.providers import ProviderError

class MarketFeed:
    def __init__(self): self.failed=False; self.resolution=None; self.price='.20'
    def markets(self):
        if self.failed: raise ProviderError('Gemini unavailable')
        return [{'id':'GEMI-TEST-A','event_ticker':'TEST','title':'Will the team win?','label':'Team wins','category':'Sports','topic':'sports','outcome':'yes','price':self.price,'sell_price':'.15','closes_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),'volume':100,'quantity_minimum':'1','quantity_increment':'1','price_increment':'.01','price_minimum':'.01','status':'active','resolution':self.resolution}]
    def market(self,id,outcome): return self.markets()[0]
    def event(self,ticker): return self.markets()

@pytest.fixture
def setup(tmp_path):
    feed=MarketFeed(); app=create_app('sqlite:///'+str(tmp_path/'test.db'),feed=feed)
    with TestClient(app) as client: yield client,feed

def user(c,name='Alex',cap=100):
    r=c.post('/users',json={'name':name,'interests':['sports'],'weekly_cap_cents':cap}); assert r.status_code==201,r.text
    return r.json()['id']
def purchase(c,u,amount='4.63',source_id=None):
    r=c.post('/purchases',json={'user_id':u,'amount':amount,'merchant':'Starbucks','source_id':source_id}); assert r.status_code==201,r.text
    return r.json()

def test_purchases_are_computed_and_deduplicated(setup):
    c,_=setup; u=user(c); a=purchase(c,u,source_id='same'); b=purchase(c,u,source_id='same')
    assert a['roundup_cents']==37 and a['id']==b['id']
    assert len(c.get('/transactions',params={'user_id':u}).json())==1
    conflict=c.post('/purchases',json={'user_id':u,'amount':'7.50','merchant':'Starbucks','source_id':'same'})
    assert conflict.status_code==409

def test_savings_allocation_is_once_and_users_are_isolated(setup):
    c,_=setup; u=user(c); other=user(c,'Blair'); p=purchase(c,u)
    payload={'user_id':u,'destination':'savings'}
    assert c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':other,'destination':'savings'}).status_code==404
    assert c.post('/roundups/'+p['roundup_id']+'/allocate',json=payload).status_code==200
    assert c.post('/roundups/'+p['roundup_id']+'/allocate',json=payload).status_code==409
    d=c.get('/dashboard',params={'user_id':u}).json(); assert d['savings_cents']==37 and d['savings_comparison_cents']==37
    assert c.get('/dashboard',params={'user_id':other}).json()['pot_cents']==0

def test_market_uses_live_price_fee_and_rollover(setup):
    c,feed=setup; u=user(c); p=purchase(c,u,'4.01'); feed.price='.40'
    r=c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'market','market_id':'GEMI-TEST-A','outcome':'yes','max_price':'.40'})
    assert r.status_code==200,r.text
    d=c.get('/dashboard',params={'user_id':u}).json()
    assert d['rollover_cents']==15 and d['weekly_spent_cents']==84
    assert d['positions'][0]['quantity']==2 and d['positions'][0]['fee_cents']==4

def test_cap_pause_and_whole_dollar(setup):
    c,_=setup; u=user(c,cap=0); p=purchase(c,u)
    assert c.get('/suggestions',params={'user_id':u,'roundup_id':p['roundup_id']}).json()['markets']==[]
    assert c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'market','market_id':'GEMI-TEST-A'}).status_code==409
    c.patch('/users/'+u,json={'weekly_cap_cents':100,'paused':True})
    assert c.get('/suggestions',params={'user_id':u,'roundup_id':p['roundup_id']}).json()['reason']=='paused'
    assert purchase(c,u,'5')['allocation']=='no_change'

def test_failure_never_fakes_markets_and_savings_still_works(setup):
    c,f=setup; u=user(c); p=purchase(c,u); f.failed=True
    assert c.get('/suggestions',params={'user_id':u,'roundup_id':p['roundup_id']}).status_code==503
    assert c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'savings'}).status_code==200

def test_settlement_credits_once(setup):
    c,f=setup; u=user(c); p=purchase(c,u,'4.01')
    r=c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'market','market_id':'GEMI-TEST-A'}); assert r.status_code==200
    f.resolution='yes'
    first=c.get('/dashboard',params={'user_id':u}).json(); second=c.get('/dashboard',params={'user_id':u}).json()
    assert first['rollover_cents']==second['rollover_cents']==414
    assert first['wins']==1 and first['positions'][0]['status']=='won'

def test_price_change_requires_a_new_choice(setup):
    c,f=setup; u=user(c); p=purchase(c,u); f.price='.30'
    r=c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'market','market_id':'GEMI-TEST-A','max_price':'.20'})
    assert r.status_code==409
    assert c.get('/transactions',params={'user_id':u}).json()[0]['allocation']=='pending'

def test_plaid_missing_credentials_is_actionable(setup,monkeypatch):
    monkeypatch.delenv('PLAID_CLIENT_ID',raising=False)
    monkeypatch.delenv('PLAID_SECRET',raising=False)
    c,_=setup; u=user(c)
    r=c.post('/demo/seed',json={'user_id':u})
    assert r.status_code==503 and 'PLAID' in r.json()['detail']

def test_confirmation_cannot_spend_more_than_preview(setup):
    from sqlalchemy.orm import Session
    from app.database import Pot
    c,f=setup;u=user(c,cap=1000);p=purchase(c,u)
    preview=c.get('/suggestions',params={'user_id':u,'roundup_id':p['roundup_id']}).json()['markets'][0]['quote']
    with Session(c.app.state.engine) as s:
        s.get(Pot,u).rollover_cents=400;s.commit()
    r=c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'market','market_id':'GEMI-TEST-A','max_quantity':preview['quantity'],'max_total_cents':preview['total_cents']})
    assert r.status_code==200,r.text
    assert r.json()['quantity']==preview['quantity']
    assert c.get('/dashboard',params={'user_id':u}).json()['weekly_spent_cents']<=preview['total_cents']

def test_small_roundups_can_be_held_and_combined(setup):
    c,f=setup;u=user(c);f.price='.50';p=purchase(c,u)
    assert c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'rollover'}).status_code==200
    next_purchase=purchase(c,u)
    result=c.get('/suggestions',params={'user_id':u,'roundup_id':next_purchase['roundup_id']}).json()
    assert result['budget_cents']==74 and result['markets'][0]['quote']['quantity']==1
