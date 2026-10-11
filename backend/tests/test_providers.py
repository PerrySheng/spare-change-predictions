from app.providers import Gemini,ProviderError
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
