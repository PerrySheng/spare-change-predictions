import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.database import PlaidItem
from app.main import create_app
from test_api import MarketFeed,user,purchase
class PlaidUpdates:
    def __init__(self,modified): self.modified=modified
    def sync(self,access_token,cursor): return {'added':[],'modified':[self.modified],'removed':[],'cursor':'next'}
@pytest.mark.parametrize('changed',[{'amount':-4.63,'iso_currency_code':'USD','pending':False},{'amount':4.63,'iso_currency_code':'EUR','pending':False},{'amount':4.63,'iso_currency_code':'USD','pending':True},{'amount':0.004,'iso_currency_code':'USD','pending':False}])
def test_modified_ineligible_purchase_cannot_be_allocated(tmp_path,changed):
    app=create_app('sqlite:///'+str(tmp_path/'p.db'),feed=MarketFeed(),plaid=PlaidUpdates({'transaction_id':'t',**changed}))
    with TestClient(app) as c:
        u=user(c);p=c.post('/purchases',json={'user_id':u,'source':'plaid','source_id':'t','merchant':'Shop','amount':'4.63'}).json()
        with Session(app.state.engine) as s:
            s.add(PlaidItem(item_id='item',user_id=u,access_token='test-only',cursor='old'));s.commit()
        assert c.post('/plaid/sync',json={'user_id':u}).status_code==200
        assert c.post('/roundups/'+p['roundup_id']+'/allocate',json={'user_id':u,'destination':'savings'}).status_code==409
        assert c.get('/dashboard',params={'user_id':u}).json()['pending_cents']==0

@pytest.mark.parametrize('amount,cents,change',[(97.66696,9767,33),(4.780789,478,22),(4.005,401,99)])
def test_fractional_cent_bank_amounts_import_as_usd_cents(tmp_path,amount,cents,change):
    row={'transaction_id':'fractional','amount':amount,'iso_currency_code':'USD','pending':False,'name':'Provider purchase','merchant_name':None,'personal_finance_category':None}
    app=create_app('sqlite:///'+str(tmp_path/'fractional.db'),feed=MarketFeed(),plaid=PlaidUpdates(row))
    with TestClient(app) as c:
        u=user(c)
        with Session(app.state.engine) as s:
            s.add(PlaidItem(item_id='item',user_id=u,access_token='test-only',cursor='old'));s.commit()
        result=c.post('/plaid/sync',json={'user_id':u})
        assert result.status_code==200,result.text
        transactions=c.get('/transactions',params={'user_id':u}).json()
        assert len(transactions)==1
        assert transactions[0]['amount_cents']==cents and transactions[0]['roundup_cents']==change
        assert c.post('/plaid/sync',json={'user_id':u}).json()['created']==0

def test_modified_fractional_cent_amount_updates_unallocated_roundup(tmp_path):
    row={'transaction_id':'t','amount':91.52556,'iso_currency_code':'USD','pending':False,'name':'Provider purchase','merchant_name':None,'personal_finance_category':None}
    app=create_app('sqlite:///'+str(tmp_path/'modified.db'),feed=MarketFeed(),plaid=PlaidUpdates(row))
    with TestClient(app) as c:
        u=user(c)
        c.post('/purchases',json={'user_id':u,'source':'plaid','source_id':'t','merchant':'Shop','amount':'4.63'})
        with Session(app.state.engine) as s:
            s.add(PlaidItem(item_id='item',user_id=u,access_token='test-only',cursor='old'));s.commit()
        result=c.post('/plaid/sync',json={'user_id':u})
        assert result.status_code==200,result.text
        transactions=c.get('/transactions',params={'user_id':u}).json()
        assert len(transactions)==1 and transactions[0]['amount_cents']==9153
        assert transactions[0]['roundup_cents']==47

@pytest.mark.parametrize('amount',[float('nan'),float('inf')])
def test_invalid_bank_amounts_fail_without_creating_purchases(tmp_path,amount):
    row={'transaction_id':'invalid','amount':amount,'iso_currency_code':'USD','pending':False,'name':'Provider purchase'}
    app=create_app('sqlite:///'+str(tmp_path/'invalid.db'),feed=MarketFeed(),plaid=PlaidUpdates(row))
    with TestClient(app) as c:
        u=user(c)
        with Session(app.state.engine) as s:
            s.add(PlaidItem(item_id='item',user_id=u,access_token='test-only',cursor='old'));s.commit()
        assert c.post('/plaid/sync',json={'user_id':u}).status_code==503
        assert c.get('/transactions',params={'user_id':u}).json()==[]
