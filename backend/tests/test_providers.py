from app.providers import Gemini,ProviderError
from app import providers
import base64,json
import pytest

def test_normalization_preserves_both_outcomes_and_does_not_invent_quotes():
    data={'title':'Will it rain?','ticker':'RAIN','category':'Weather','volume':'12.40','expiryDate':'2027-01-01T00:00:00Z','contracts':[{'instrumentSymbol':'GEMI-RAIN','label':'Rain','status':'active','prices':{'buy':{'yes':'.40'},'sell':{'yes':'.35'}},'quantityMinimum':'1','quantityIncrement':'1'}]}
    rows=Gemini().normalize(data)
    assert rows[0]['price']=='.40' and rows[0]['sell_price']=='.35'
    assert rows[1]['outcome']=='no' and rows[1]['price'] is None
    assert rows[0]['volume']=='12.40' and rows[0]['topic']=='weather'

def test_sandbox_orders_never_use_production_quotes():
    with pytest.raises(ProviderError,match='sandbox market prices'):
        Gemini('https://api.gemini.com').place_order({'id':'some-symbol','price':'.2','outcome':'yes'},1)

def test_private_api_missing_keys_does_not_send_a_request(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False);monkeypatch.delenv('GEMINI_API_SECRET',raising=False)
    with pytest.raises(ProviderError,match='GEMINI_API_KEY'): Gemini().private('/v1/prediction-markets/order')

@pytest.mark.parametrize('path,method', [('/v1/prediction-markets/terms/status','GET'),('/v1/prediction-markets/order','POST')])
def test_master_prediction_requests_target_configured_account(monkeypatch,path,method):
    monkeypatch.setenv('GEMINI_API_KEY','master-controlled-key')
    monkeypatch.setenv('GEMINI_API_SECRET','controlled-secret')
    monkeypatch.setenv('GEMINI_ACCOUNT','research-account')
    observed=[]
    def request(method,url,**kwargs):
        payload=json.loads(base64.b64decode(kwargs['headers']['X-GEMINI-PAYLOAD']))
        observed.append((method,url,payload,kwargs['content']))
        return {'hasAcceptedLatest':True}
    monkeypatch.setattr(providers,'http_json',request)
    params={'symbol':'GEMI-CONTROLLED'}
    Gemini(Gemini.SANDBOX).private(path,params,method=method)
    assert observed[0][0]==method and observed[0][1]==Gemini.SANDBOX+path
    assert observed[0][2]['account']=='research-account'
    assert observed[0][2]['symbol']=='GEMI-CONTROLLED' and observed[0][3]==b''
    assert params=={'symbol':'GEMI-CONTROLLED'}

def test_master_prediction_missing_account_fails_before_network(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','master-controlled-key')
    monkeypatch.setenv('GEMINI_API_SECRET','controlled-secret')
    monkeypatch.delenv('GEMINI_ACCOUNT',raising=False)
    calls=[]
    monkeypatch.setattr(providers,'http_json',lambda *a,**k: calls.append(a) or {})
    with pytest.raises(ProviderError,match='GEMINI_ACCOUNT'):
        Gemini(Gemini.SANDBOX).private('/v1/prediction-markets/order')
    assert calls==[]

def test_account_key_and_master_discovery_do_not_receive_default_account(monkeypatch):
    monkeypatch.setenv('GEMINI_API_SECRET','controlled-secret')
    monkeypatch.setenv('GEMINI_ACCOUNT','research-account')
    payloads=[]
    def request(method,url,**kwargs):
        payloads.append(json.loads(base64.b64decode(kwargs['headers']['X-GEMINI-PAYLOAD'])))
        return {}
    monkeypatch.setattr(providers,'http_json',request)
    monkeypatch.setenv('GEMINI_API_KEY','account-controlled-key')
    Gemini(Gemini.SANDBOX).private('/v1/prediction-markets/terms/status',method='GET')
    monkeypatch.setenv('GEMINI_API_KEY','master-controlled-key')
    Gemini(Gemini.SANDBOX).private('/v1/account/list')
    assert all('account' not in p for p in payloads)
