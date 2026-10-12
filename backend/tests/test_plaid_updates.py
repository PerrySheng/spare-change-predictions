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

@pytest.mark.parametrize('name,category', [('Interest charged',None),('Interest',None),('Card fee',{'primary':'BANK_FEES','detailed':'BANK_FEES_INTEREST_CHARGE'}),('Account transfer',{'primary':'TRANSFER_OUT'})])
def test_financial_entries_are_not_imported_as_purchase_roundups(tmp_path,name,category):
    row={'transaction_id':'fee','amount':20.47,'iso_currency_code':'USD','pending':False,'name':name,'merchant_name':None,'personal_finance_category':category}
    app=create_app('sqlite:///'+str(tmp_path/'fees.db'),feed=MarketFeed(),plaid=PlaidUpdates(row))
    with TestClient(app) as c:
        u=user(c)
        with Session(app.state.engine) as s:
            s.add(PlaidItem(item_id='item',user_id=u,access_token='test-only',cursor='old'));s.commit()
        assert c.post('/plaid/sync',json={'user_id':u}).json()['created']==0
        assert c.get('/transactions',params={'user_id':u}).json()==[]
        assert c.get('/dashboard',params={'user_id':u}).json()['pending_cents']==0

def test_plaid_purchase_uses_a_clean_real_merchant_name(tmp_path):
    row={'transaction_id':'shop','amount':4.63,'iso_currency_code':'USD','pending':False,'name':'POS RAW DESCRIPTION','merchant_name':'  Blue   Bottle Coffee  ','personal_finance_category':{'primary':'FOOD_AND_DRINK'}}
    app=create_app('sqlite:///'+str(tmp_path/'named.db'),feed=MarketFeed(),plaid=PlaidUpdates(row))
    with TestClient(app) as c:
        u=user(c)
        with Session(app.state.engine) as s:
            s.add(PlaidItem(item_id='item',user_id=u,access_token='test-only',cursor='old'));s.commit()
        assert c.post('/plaid/sync',json={'user_id':u}).status_code==200
        assert c.get('/transactions',params={'user_id':u}).json()[0]['merchant']=='Blue Bottle Coffee'

def test_legacy_financial_entries_are_flagged_and_not_available_change(tmp_path):
    app=create_app('sqlite:///'+str(tmp_path/'legacy.db'),feed=MarketFeed())
    with TestClient(app) as c:
        u=user(c)
        c.post('/purchases',json={'user_id':u,'source':'plaid','source_id':'old-interest','merchant':'Interest charged','amount':'20.47','category':'BANK_FEES'})
        transactions=c.get('/transactions',params={'user_id':u}).json()
        assert transactions[0]['is_purchase'] is False
        assert c.get('/dashboard',params={'user_id':u}).json()['pending_cents']==0
        assert c.get('/dashboard',params={'user_id':u}).json()['savings_comparison_cents']==0

class DelayedDemoPlaid:
    def __init__(self):self.calls=0;self.requested=[]
    def connect(self,webhook):return {'access_token':'test-only','item_id':'item'}
    def create_purchases(self,access,purchases):self.requested=purchases
    def sync(self,access,cursor=''):
        self.calls+=1
        if self.calls==1:rows=[]
        elif self.calls==2:
            rows=[{'transaction_id':f'bootstrap-{i}','amount':10.47,'name':'Bank generated history','merchant_name':'Historical shop','pending':False,'iso_currency_code':'USD','personal_finance_category':None} for i in range(5)]
        else:
            rows=[{'transaction_id':f'demo-{i}','amount':p['amount'],'name':p['merchant'],'merchant_name':p['merchant'],'original_description':p.get('description',p['merchant']),'pending':False,'iso_currency_code':'USD','personal_finance_category':None} for i,p in enumerate(self.requested)]
        return {'added':rows,'modified':[],'removed':[],'cursor':f'c{self.calls}'}

def test_demo_waits_for_three_named_purchases_instead_of_importing_sandbox_history(tmp_path,monkeypatch):
    monkeypatch.setattr('app.main.time.sleep',lambda _:None)
    app=create_app('sqlite:///'+str(tmp_path/'demo.db'),feed=MarketFeed(),plaid=DelayedDemoPlaid())
    with TestClient(app) as c:
        u=user(c)
        response=c.post('/demo/seed',json={'user_id':u})
        assert response.status_code==200
        assert response.json()['created']==3
        rows=c.get('/transactions',params={'user_id':u}).json()
        assert sorted((r['merchant'],r['roundup_cents']) for r in rows)==[('Shell',44),('Starbucks',37),('Ticketmaster',79)]
