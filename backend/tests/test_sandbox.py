import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.providers import ProviderError,ProviderRejected
from test_api import MarketFeed,user,purchase
class SandboxFeed(MarketFeed):
    def __init__(self): super().__init__(); self.response={'orderId':101,'status':'filled','filledQuantity':'4','avgExecutionPrice':'.20'}; self.calls=0; self.ready=True
    def ensure_trading_ready(self):
        if not self.ready: raise ProviderError('Review and accept the latest terms first.')
    def place_order(self,m,q):
        self.calls+=1
        if self.response=='timeout': raise ProviderError('Provider is unreachable')
        if self.response=='rejected': raise ProviderRejected('Provider returned HTTP 400: InsufficientFunds')
        return self.response
    def lookup_order(self,id,oid): return self.response
@pytest.fixture
def sandbox(tmp_path,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-only');monkeypatch.setenv('GEMINI_API_SECRET','test-only')
    f=SandboxFeed()
    with TestClient(create_app('sqlite:///'+str(tmp_path/'sandbox.db'),feed=f,mode='sandbox')) as c: yield c,f
def allocate(c,u,p): return c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'market','market_id':'GEMI-TEST-A'})
def test_confirmed_sandbox_fill_uses_actual_fill_price(sandbox):
    c,f=sandbox;u=user(c);p=purchase(c,u,'4.01');f.response['avgExecutionPrice']='.19'
    r=allocate(c,u,p); assert r.status_code==200,r.text;assert r.json()['status']=='filled'
    d=c.get('/dashboard',params={'user_id':u}).json();assert d['positions'][0]['mode']=='sandbox' and d['positions'][0]['cost_cents']==76 and d['rollover_cents']==18
def test_cancelled_order_keeps_change_and_cap(sandbox):
    c,f=sandbox;u=user(c);p=purchase(c,u,'4.01');f.response={'orderId':101,'status':'cancelled','filledQuantity':'0'}
    assert allocate(c,u,p).json()['status']=='cancelled'
    d=c.get('/dashboard',params={'user_id':u}).json();assert d['rollover_cents']==99 and d['weekly_spent_cents']==0 and d['positions']==[]
def test_timeout_never_retries_or_counts_as_a_fill(sandbox):
    c,f=sandbox;u=user(c);p=purchase(c,u,'4.01');f.response='timeout'
    assert allocate(c,u,p).json()['status']=='unknown'
    assert allocate(c,u,p).status_code==409 and f.calls==1
    d=c.get('/dashboard',params={'user_id':u}).json();assert d['total_value_cents'] is None and d['positions']==[] and d['weekly_spent_cents']==85
def test_terms_preflight_does_not_lock_change(sandbox):
    c,f=sandbox;u=user(c);p=purchase(c,u,'4.01');f.ready=False
    assert allocate(c,u,p).status_code==503
    d=c.get('/dashboard',params={'user_id':u}).json();assert d['weekly_spent_cents']==0 and d['pending_cents']==99
def test_definite_rejection_releases_reservation(sandbox):
    c,f=sandbox;u=user(c);p=purchase(c,u,'4.01');f.response='rejected'
    r=allocate(c,u,p);assert r.json()['status']=='rejected'
    d=c.get('/dashboard',params={'user_id':u}).json();assert d['weekly_spent_cents']==0 and d['rollover_cents']==99
