from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from app.money import parse_cents, roundup_cents, order_quote
from app.scoring import rank_markets

@pytest.mark.parametrize('value,cents,change', [('4.63',463,37),('$1,234.01',123401,99),('12',1200,0),('0.99',99,1),('USD 8.20',820,80)])
def test_money_and_roundup(value,cents,change):
    assert parse_cents(value) == cents
    assert roundup_cents(cents) == change

@pytest.mark.parametrize('bad',['-3.20','NaN','1e3','3.001','€4.63','4,63','abc','0','1 2.30'])
def test_rejects_invalid_currency(bad):
    with pytest.raises(ValueError): parse_cents(bad)

def test_quote_accounts_for_fees_and_keeps_remainder():
    assert order_quote(100,Decimal('.40')) == {'quantity':2,'cost_cents':80,'fee_cents':4,'total_cents':84,'leftover_cents':16}
    assert order_quote(40,Decimal('.40'))['quantity'] == 0
    assert order_quote(42,Decimal('.40'))['quantity'] == 1

def test_quote_respects_instrument_quantity_grid():
    assert order_quote(200,Decimal('.40'),quantity_minimum=Decimal('3'))['quantity'] == 4
    assert order_quote(100,Decimal('.40'),quantity_minimum=Decimal('3'))['quantity'] == 0
    assert order_quote(300,Decimal('.40'),quantity_increment=Decimal('2'))['quantity'] == 6

NOW=datetime(2026,10,11,19,tzinfo=timezone.utc)
def market(i,topic,price='.20',days=3,volume=100):
    return {'id':i,'event_ticker':i,'title':i,'category':topic,'topic':topic,'price':price,'outcome':'yes','closes_at':(NOW+timedelta(days=days)).isoformat(),'volume':volume,'quantity_minimum':'1','quantity_increment':'1'}

def test_interests_change_ranking():
    markets=[market('ball','sports'),market('coin','crypto')]
    assert rank_markets(markets, ['sports'], [], [], 50, now=NOW)[0]['id']=='ball'
    assert rank_markets(markets, ['crypto'], [], [], 50, now=NOW)[0]['id']=='coin'

def test_spending_and_past_picks_change_scores():
    markets=[market('rates','economy'),market('rain','weather')]
    food=[{'amount_cents':463,'merchant':'Starbucks','category':'FOOD_AND_DRINK'}]
    travel=[{'amount_cents':20000,'merchant':'United Airlines','category':'TRAVEL'}]
    assert rank_markets(markets,[],food,[],50,now=NOW)[0]['id']=='rates'
    assert rank_markets(markets,[],travel,[],50,now=NOW)[0]['id']=='rain'
    assert rank_markets(markets,[],[],['weather'],50,now=NOW)[0]['id']=='rain'

def test_unaffordable_expired_and_repeated_events_are_excluded():
    a=market('a','sports'); b=market('b','sports'); b['event_ticker']='a'
    result=rank_markets([a,b,market('costly','crypto','.99'),market('ended','weather',days=-1)],['crypto'],[],[],30,now=NOW)
    assert len(result)==1
    assert result[0]['quote']['total_cents']<=30
    assert result[0]['score']==round(sum(result[0]['factors'].values()),4)

def test_no_loss_input_and_all_reasons_derive_from_evidence():
    result=rank_markets([market('a','sports')],['sports'],[],[],50,now=NOW)[0]
    assert 'sports' in result['why'].lower()
    assert set(result['factors'])=={'interest','spending','past_picks','affordability','closes_soon','liquidity'}
