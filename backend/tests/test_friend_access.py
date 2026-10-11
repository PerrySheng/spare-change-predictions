import pytest
from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient
from app.main import create_app
from test_api import MarketFeed

@pytest.fixture
def protected(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('APP_SESSION_SECRET','test-signing-secret-with-at-least-32-characters')
    monkeypatch.setenv('DEMO_ACCESS_CODE','test-friend-code-only')
    app=create_app('sqlite:///'+str(tmp_path/'friends.db'),feed=MarketFeed(),mode='paper')
    return app

def enter(c,name):
    r=c.post('/access',data={'code':'test-friend-code-only'},follow_redirects=False)
    assert r.status_code==303
    assert 'HttpOnly' in r.headers['set-cookie'] and 'Secure' in r.headers['set-cookie']
    r=c.post('/users',json={'name':name,'interests':['sports']})
    assert r.status_code==201
    return r.json()['id']

def test_separate_sessions_can_use_own_profiles_but_cannot_impersonate(protected):
    with TestClient(protected,base_url='https://friends.test') as a,TestClient(protected,base_url='https://friends.test') as b:
        assert a.get('/health').status_code==200
        assert a.get('/dashboard?user_id=anything').status_code==401
        one=enter(a,'Alex');two=enter(b,'Blair')
        assert a.get('/users/'+one).status_code==200
        assert b.get('/users/'+one).status_code==404
        assert a.post('/purchases',json={'user_id':two,'amount':'4.63','merchant':'Shop'}).status_code==404
        assert b.post('/purchases',json={'user_id':two,'amount':'4.63','merchant':'Shop'}).status_code==201
        squad=a.post('/squads',json={'user_id':one,'name':'Invite protected','stake_cents':1500,'member_limit':3,'lock_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}).json()
        assert b.post('/squads/'+squad['id']+'/join',json={'user_id':two}).status_code==403
        assert b.post('/squads/join',json={'user_id':two,'invite_code':squad['invite_code']}).status_code==200
        assert a.get('/dashboard',params={'user_id':one}).json()['available_cents']==0
        assert b.get('/dashboard',params={'user_id':two}).json()['available_cents']==37

def test_wrong_access_and_cross_origin_writes_are_rejected(protected):
    with TestClient(protected,base_url='https://friends.test') as c:
        assert c.post('/access',data={'code':'incorrect'}).status_code==401
        assert c.post('/access',data={'code':'🐝'}).status_code==401
        u=enter(c,'Alex')
        assert c.post('/purchases',json={'user_id':u,'amount':'4.63','merchant':'Shop'},headers={'Origin':'https://attacker.test'}).status_code==403
        c.cookies.set('spare-profile','profile:'+u+'.forged',domain='friends.test')
        assert c.get('/dashboard',params={'user_id':u}).status_code==401

def test_production_does_not_start_without_required_private_access(monkeypatch):
    monkeypatch.setenv('APP_ENV','production');monkeypatch.delenv('APP_SESSION_SECRET',raising=False)
    with pytest.raises(ValueError,match='Production requires'):
        create_app('sqlite:///:memory:',feed=MarketFeed())

def test_squad_invite_also_opens_the_app_for_a_new_friend(protected):
    with TestClient(protected,base_url='https://friends.test') as a,TestClient(protected,base_url='https://friends.test') as b:
        u=enter(a,'Alex')
        squad=a.post('/squads',json={'user_id':u,'name':'Friends','stake_cents':1500,'member_limit':2,'lock_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}).json()
        r=b.post('/access',data={'code':squad['invite_code']},follow_redirects=False)
        assert r.status_code==303
        assert b.get('/access/invite').json()['invite_code']==squad['invite_code']
        v=b.post('/users',json={'name':'Blair','interests':[]}).json()['id']
        joined=b.post('/squads/join',json={'user_id':v,'invite_code':squad['invite_code']})
        assert joined.status_code==200 and len(joined.json()['members'])==2


def test_public_demo_opens_without_code_but_uses_protected_separate_profiles(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('APP_PUBLIC_DEMO','true')
    monkeypatch.setenv('APP_SESSION_SECRET','public-demo-signing-secret-at-least-32-chars')
    app=create_app('sqlite:///'+str(tmp_path/'public.db'),feed=MarketFeed(),mode='paper')
    with TestClient(app,base_url='https://public.test') as a,TestClient(app,base_url='https://public.test') as b:
        assert a.get('/',headers={'Accept':'text/html'},follow_redirects=False).status_code==200
        assert a.get('/dashboard?user_id=anything').status_code==401
        ra=a.post('/users',json={'name':'Alex','interests':[]});rb=b.post('/users',json={'name':'Blair','interests':[]})
        assert ra.status_code==rb.status_code==201
        assert 'HttpOnly' in ra.headers['set-cookie'] and 'Secure' in ra.headers['set-cookie']
        one=ra.json()['id'];two=rb.json()['id']
        assert a.get('/users/'+one).status_code==200
        assert b.get('/users/'+one).status_code==404
        assert b.post('/purchases',json={'user_id':one,'amount':'4.63','merchant':'Shop'}).status_code==404
        assert b.post('/purchases',json={'user_id':two,'amount':'4.63','merchant':'Shop'}).status_code==201
