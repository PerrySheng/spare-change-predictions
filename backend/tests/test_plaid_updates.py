import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.database import PlaidItem
from app.main import create_app
from test_api import MarketFeed,user,purchase
class PlaidUpdates:
    def __init__(self,modified): self.modified=modified
    def sync(self,access_token,cursor): return {'added':[],'modified':[self.modified],'removed':[],'cursor':'next'}
@pytest.mark.parametrize('changed',[{'amount':-4.63,'iso_currency_code':'USD','pending':False},{'amount':4.63,'iso_currency_code':'EUR','pending':False},{'amount':4.63,'iso_currency_code':'USD','pending':True}])
def test_modified_ineligible_purchase_cannot_be_allocated(tmp_path,changed):
    app=create_app('sqlite:///'+str(tmp_path/'p.db'),feed=MarketFeed(),plaid=PlaidUpdates({'transaction_id':'t',**changed}))
    with TestClient(app) as c:
        u=user(c);p=c.post('/purchases',json={'user_id':u,'source':'plaid','source_id':'t','merchant':'Shop','amount':'4.63'}).json()
        with Session(app.state.engine) as s:
            s.add(PlaidItem(item_id='item',user_id=u,access_token='test-only',cursor='old'));s.commit()
        assert c.post('/plaid/sync',json={'user_id':u}).status_code==200
        assert c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'savings'}).status_code==409
        assert c.get('/dashboard',params={'user_id':u}).json()['pending_cents']==0
