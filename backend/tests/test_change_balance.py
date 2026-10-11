from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from app.main import create_app
from test_api import MarketFeed,user,purchase

def test_onboarding_needs_no_cap_and_purchase_change_accumulates(tmp_path):
    with TestClient(create_app('sqlite:///'+str(tmp_path/'balance.db'),feed=MarketFeed())) as c:
        r=c.post('/users',json={'name':'Alex','interests':['sports']})
        assert r.status_code==201
        u=r.json()['id']
        purchase(c,u,'4.63',source_id='one')
        purchase(c,u,'4.63',source_id='one')
        purchase(c,u,'18.21',source_id='two')
        purchase(c,u,'5.00',source_id='whole')
        d=c.get('/dashboard',params={'user_id':u}).json()
        assert d['available_cents']==116 and d['total_value_cents']==116
        assert d['savings_comparison_cents']==116
        assert 'weekly_cap_cents' not in r.json() and 'remaining_cap_cents' not in d

def test_all_pending_change_funds_one_bet_without_a_weekly_cap(tmp_path):
    with TestClient(create_app('sqlite:///'+str(tmp_path/'pool.db'),feed=MarketFeed())) as c:
        u=user(c,cap=0);other=user(c,'Blair',cap=0)
        first=purchase(c,u,'4.63');purchase(c,u,'4.79');purchase(c,other,'4.01')
        s=c.get('/suggestions',params={'user_id':u,'roundup_id':first['roundup_id']}).json()
        assert s['budget_cents']==58 and s['markets']
        q=c.get('/markets/quote',params={'user_id':u,'roundup_id':first['roundup_id'],'market_id':'GEMI-TEST-A','amount_cents':58})
        assert q.status_code==200 and q.json()['available_cents']==58
        r=c.post('/roundups/'+first['roundup_id']+'/allocate',json={'user_id':u,'destination':'market','market_id':'GEMI-TEST-A','amount_cents':58})
        assert r.status_code==200
        d=c.get('/dashboard',params={'user_id':u}).json()
        assert d['rollover_cents']==15 and d['pending_cents']==0 and d['available_cents']==15
        assert d['positions'][0]['quantity']==2 and d['savings_comparison_cents']==58
        assert c.get('/dashboard',params={'user_id':other}).json()['available_cents']==99

def test_saved_change_is_not_available_to_spend_and_failed_bet_keeps_the_pool(tmp_path):
    with TestClient(create_app('sqlite:///'+str(tmp_path/'saved.db'),feed=MarketFeed())) as c:
        u=user(c);saved=purchase(c,u,'4.63');c.post('/roundups/'+saved['roundup_id']+'/allocate',json={'user_id':u,'destination':'savings'})
        current=purchase(c,u,'4.01')
        r=c.post('/roundups/'+current['roundup_id']+'/allocate',json={'user_id':u,'destination':'market','market_id':'GEMI-TEST-A','amount_cents':100})
        assert r.status_code==409
        d=c.get('/dashboard',params={'user_id':u}).json()
        assert d['available_cents']==99 and d['savings_cents']==37 and d['pending_cents']==99

def test_concurrent_bets_cannot_spend_the_same_accumulated_change(tmp_path):
    with TestClient(create_app('sqlite:///'+str(tmp_path/'race.db'),feed=MarketFeed())) as c:
        u=user(c,cap=0);roundups=[purchase(c,u,'4.63'),purchase(c,u,'4.63')]
        def bet(p):return c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'market','market_id':'GEMI-TEST-A','amount_cents':73}).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:codes=list(executor.map(bet,roundups))
        assert sorted(codes)==[200,409]
        d=c.get('/dashboard',params={'user_id':u}).json()
        assert len(d['positions'])==1 and d['rollover_cents']==10 and d['pending_cents']==0
