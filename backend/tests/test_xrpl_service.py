import base64
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.database import User, build_engine
from app.squad_models import Squad, SquadMember, SquadLeg
from app.xrpl_models import XRPLWallet, XRPLEscrow, XRPLOperation, XRPLSettlement
from app.xrpl_service import register_xrpl


class Feed:
    def __init__(self): self.results = {'m1': None, 'm2': None, 'm3': None}; self.calls = []
    def event(self, ticker):
        self.calls.append(ticker)
        resolution = self.results.get(ticker.lower())
        return [{'id': ticker.lower(), 'event_ticker': ticker, 'outcome': side, 'resolution': resolution, 'status': 'resolved' if resolution else 'active'} for side in ['yes', 'no']]


class Executor:
    def __init__(self): self.calls = []; self.counter = 0; self.fail = None; self.engine = None
    def __call__(self, payload):
        self.calls.append(payload.copy())
        if payload['operation'] not in ['probe', 'account']:
            # The durable intent must exist before any external transaction.
            with Session(self.engine) as s:
                assert s.query(XRPLOperation).filter_by(status='pending').count() > 0
        status = {'network': 'testnet', 'network_id': 1, 'ledger_close_time': int(datetime.now(timezone.utc).timestamp())-946684800, 'amendments': {'TokenEscrow': True, 'BatchV1_1': True}}
        if payload['operation'] == 'probe': return {'ok': True, 'status': status, 'transactions': []}
        if payload['operation'] == 'account': return {'ok': True, 'status': status, 'xrp_balance': '100', 'token_balance': '100', 'transactions': []}
        self.counter += 1
        hash = f'{self.counter:064X}'
        record = {'hash': hash, 'type': payload['operation'], 'result': 'tesSUCCESS', 'ledger_index': 1}
        if self.fail and (not isinstance(self.fail,tuple) or self.fail[0]==payload['operation']):
            fail = self.fail[-1] if isinstance(self.fail,tuple) else self.fail; self.fail = None
            if fail == 'timeout': raise TimeoutError('unknown submission')
            if fail == 'unconfirmed': return {'ok': False, 'error': 'Transport failure', 'transactions': [{**record, 'result': 'submitted_unconfirmed'}]}
            if fail == 'rejected': return {'ok': False, 'error': 'Token permission rejected', 'transactions': [{**record, 'result': 'tecNO_PERMISSION'}]}
        out = {'ok': True, 'status': status, 'hash': hash, 'transactions': [record]}
        if payload['operation'] == 'setup':
            out.update(issuer={'address': 'rIssuer', 'encrypted_seed': 'encrypted-issuer'}, settlement={'address': 'rTreasury', 'encrypted_seed': 'encrypted-treasury'})
        elif payload['operation'] == 'wallet-create':
            out['wallet'] = {'address': f'rWallet{self.counter}', 'encrypted_seed': f'encrypted-{self.counter}'}
        elif payload['operation'] == 'escrow-create':
            out.update(owner='rMember', offer_sequence=self.counter, condition='A0condition', encrypted_fulfillment='encrypted-condition', cancel_after=payload['cancel_after'])
        elif payload['operation'] == 'batch-payout':
            out['inner_transactions'] = [{'hash': f'{100+self.counter+i:064X}', 'result': 'tesSUCCESS', 'ledger_index': 1} for i, row in enumerate(payload['payouts']) if row['cents']]
            out['balances'] = [{'address': row['address'], 'before': '0', 'after': str(row['cents']/100), 'payout_cents': row['cents']} for row in payload['payouts']]
        return out


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('XRPL_WALLET_KEY', base64.b64encode(b'x'*32).decode())
    monkeypatch.setenv('XRPL_NETWORK', 'testnet')
    engine = build_engine('sqlite:///' + str(tmp_path/'xrpl.db'))
    with Session(engine) as s:
        s.add_all([User(id=u, name=u, interests=[], weekly_cap_cents=500) for u in ['a','b','c','d']]); s.flush()
        s.add(Squad(id='squad', creator_id='a', name='Squad', invite_code='CODE', stake_cents=1500, member_limit=3, lock_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(), status='locked')); s.flush()
        for index, user in enumerate(['a','b','c'],1):
            s.add(SquadMember(squad_id='squad',user_id=user))
            s.add(SquadLeg(id=f'l{index}',squad_id='squad',user_id=user,market_id=f'm{index}',event_ticker=f'M{index}',title='Event',label='Contract',category='sports',outcome='yes',entry_price='.5',closes_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),locked=True))
        s.commit()
    executor=Executor(); executor.engine=engine; feed=Feed(); app=FastAPI(); register_xrpl(app,engine,feed,executor=executor)
    with TestClient(app) as client: yield client, executor, feed, engine


def lock_all(client):
    for user in ['a','b','c']:
        response=client.post('/squads/squad/xrpl/lock',json={'user_id':user})
        assert response.status_code==200,response.text


def test_missing_key_and_mainnet_disable_before_any_external_mutation(setup,monkeypatch):
    c,e,_,_=setup; monkeypatch.delenv('XRPL_WALLET_KEY')
    assert c.get('/xrpl/status').json()['configured'] is False
    assert c.post('/xrpl/wallet',json={'user_id':'a'}).status_code==503
    assert e.calls==[]
    monkeypatch.setenv('XRPL_NETWORK','mainnet')
    assert c.get('/xrpl/status').status_code==503


def test_wallets_are_encrypted_durable_and_idempotent(setup):
    c,e,_,engine=setup
    first=c.post('/xrpl/wallet',json={'user_id':'a'}); assert first.status_code==200,first.text
    count=len(e.calls); second=c.post('/xrpl/wallet',json={'user_id':'a'}); assert second.status_code==200
    assert first.json()['address']==second.json()['address']
    assert not any('seed' in key for key in first.json())
    assert len([v for v in e.calls[count:] if v['operation']=='wallet-create'])==0
    with Session(engine) as s: assert s.get(XRPLWallet,'member:testnet:a').encrypted_seed.startswith('encrypted-')


def test_first_lock_freezes_complete_picks_and_rejects_two_member_squad(setup):
    c,e,_,engine=setup
    with Session(engine) as s:
        s.get(Squad,'squad').status='open'; s.commit()
    response=c.post('/squads/squad/xrpl/lock',json={'user_id':'a'}); assert response.status_code==200,response.text
    with Session(engine) as s:
        assert s.get(Squad,'squad').status=='locked'
        assert s.query(SquadLeg).filter_by(locked=True).count()==3
    assert c.post('/squads/squad/xrpl/lock',json={'user_id':'d'}).status_code==404
    # Reject incompatible count before creating any collateral.
    with Session(engine) as s:
        s.add(Squad(id='two',creator_id='a',name='Two',invite_code='TWO',stake_cents=1000,member_limit=2,lock_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())); s.flush()
        s.add(SquadMember(squad_id='two',user_id='a')); s.commit()
    before=len(e.calls)
    assert c.post('/squads/two/xrpl/lock',json={'user_id':'a'}).status_code==409
    assert len(e.calls)==before


@pytest.mark.parametrize('losers,expected',[([], [1000,1000,1000]),(['m1'],[0,1500,1500]),(['m1','m2'],[750,750,1500]),(['m1','m2','m3'],[1000,1000,1000])])
def test_final_fresh_provider_results_drive_atomic_payout_once(setup,losers,expected):
    c,e,feed,engine=setup; lock_all(c)
    feed.results = {'m1':'yes','m2':'yes','m3':'yes'}
    for market in losers: feed.results[market]='no'
    first=c.post('/squads/squad/xrpl/settle',json={'user_id':'a'}); assert first.status_code==200,first.text
    assert first.json()['status']=='settled'
    batches=[call for call in e.calls if call['operation']=='batch-payout']; assert len(batches)==1
    assert [item['cents'] for item in batches[0]['payouts']]==expected
    assert set(feed.calls)=={'M1','M2','M3'}
    second=c.post('/squads/squad/xrpl/settle',json={'user_id':'a'}); assert second.status_code==200
    assert len([call for call in e.calls if call['operation']=='batch-payout'])==1
    assert 'encrypted' not in first.text and 'fulfillment' not in first.text


def test_pending_results_and_noncreator_cannot_release_collateral(setup):
    c,e,feed,_=setup; lock_all(c); feed.results['m2']=None
    before=len(e.calls)
    assert c.post('/squads/squad/xrpl/settle',json={'user_id':'b'}).status_code==403
    assert c.post('/squads/squad/xrpl/settle',json={'user_id':'a'}).status_code==409
    assert not any(call['operation']=='escrow-finish' for call in e.calls[before:])


def test_unknown_submission_is_reserved_and_never_retried(setup):
    c,e,_,engine=setup
    c.post('/xrpl/wallet',json={'user_id':'a'})
    # Create settlement account once, then fail actual escrow submission.
    c.post('/xrpl/setup',json={'user_id':'a'})
    e.fail=('escrow-create','unconfirmed')
    response=c.post('/squads/squad/xrpl/lock',json={'user_id':'a'}); assert response.status_code==503
    before=len(e.calls)
    retry=c.post('/squads/squad/xrpl/lock',json={'user_id':'a'}); assert retry.status_code==409
    assert len(e.calls)==before
    with Session(engine) as s: assert s.query(XRPLOperation).filter_by(status='unknown').count()==1


def test_refund_waits_for_deadline_and_is_member_scoped(setup):
    c,e,_,engine=setup; lock_all(c)
    assert c.post('/squads/squad/xrpl/refund',json={'user_id':'d'}).status_code==404
    assert c.post('/squads/squad/xrpl/refund',json={'user_id':'a'}).status_code==409
    with Session(engine) as s:
        s.get(XRPLSettlement,'squad').cancel_after=1
        for escrow in s.query(XRPLEscrow): escrow.cancel_after=1
        s.commit()
    for user in ['a','b','c']:
        response=c.post('/squads/squad/xrpl/refund',json={'user_id':user}); assert response.status_code==200,response.text
    assert response.json()['status']=='refunded'
    assert len([call for call in e.calls if call['operation']=='escrow-cancel'])==3


def test_expired_collateral_cannot_be_released(setup):
    c,e,_,engine=setup; lock_all(c)
    with Session(engine) as s:
        s.get(XRPLSettlement,'squad').cancel_after=1; s.commit()
    response=c.post('/squads/squad/xrpl/settle',json={'user_id':'a'})
    assert response.status_code==409
    assert not any(call['operation']=='escrow-finish' for call in e.calls)


def test_unknown_payout_never_runs_a_second_batch(setup):
    c,e,feed,engine=setup; lock_all(c); feed.results = {'m1':'yes','m2':'yes','m3':'yes'}; e.fail=('batch-payout','unconfirmed')
    response=c.post('/squads/squad/xrpl/settle',json={'user_id':'a'}); assert response.status_code==503
    with Session(engine) as s:
        assert s.get(XRPLSettlement,'squad').status=='unknown'
        assert all(row.status=='released' for row in s.query(XRPLEscrow))
    assert c.post('/squads/squad/xrpl/settle',json={'user_id':'a'}).status_code==409
    assert len([call for call in e.calls if call['operation']=='batch-payout'])==1
    detail=c.get('/squads/squad/xrpl',params={'user_id':'a'}).json()
    assert any(row['result']=='submitted_unconfirmed' and row['explorer_url'].startswith('https://testnet.xrpl.org/') for row in detail['transactions'])


def test_concurrent_member_lock_has_one_real_intent(setup):
    from concurrent.futures import ThreadPoolExecutor
    c,e,_,engine=setup
    c.post('/xrpl/wallet',json={'user_id':'a'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:c.post('/squads/squad/xrpl/lock',json={'user_id':'a'}),range(2)))
    assert all(response.status_code in [200,409] for response in responses)
    assert len([call for call in e.calls if call['operation']=='escrow-create'])==1
    with Session(engine) as s: assert s.query(XRPLEscrow).filter_by(user_id='a').count()==1


def test_any_closed_leg_prevents_collateral_before_external_calls(setup):
    c,e,_,engine=setup
    with Session(engine) as s:
        s.get(SquadLeg,'l1').closes_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat();s.commit()
    assert c.post('/squads/squad/xrpl/lock',json={'user_id':'a'}).status_code==409
    assert e.calls==[]


def test_published_early_outcome_prevents_an_escrow(setup):
    c,e,feed,_=setup; feed.results['m1']='yes'
    assert c.post('/squads/squad/xrpl/lock',json={'user_id':'a'}).status_code==409
    assert not any(call['operation']=='escrow-create' for call in e.calls)


def test_definitive_validated_rejection_can_retry_without_duplicate_lock(setup):
    c,e,_,engine=setup; e.fail=('escrow-create','rejected')
    assert c.post('/squads/squad/xrpl/lock',json={'user_id':'a'}).status_code==503
    with Session(engine) as s:
        assert s.query(XRPLEscrow).one().status=='failed'
        assert s.query(XRPLOperation).filter_by(status='failed').count()==1
    response=c.post('/squads/squad/xrpl/lock',json={'user_id':'a'});assert response.status_code==200,response.text
    with Session(engine) as s: assert s.query(XRPLEscrow).one().status=='locked'
    assert len([call for call in e.calls if call['operation']=='escrow-create'])==2


def test_void_final_leg_is_not_charged_as_a_loser(setup):
    c,e,feed,_=setup;lock_all(c);feed.results={'m1':'void','m2':'no','m3':'yes'}
    response=c.post('/squads/squad/xrpl/settle',json={'user_id':'a'});assert response.status_code==200,response.text
    assert [row['payout_cents'] for row in response.json()['plan']['members']]==[1500,0,1500]


def test_invalid_optional_network_does_not_break_squad_detail(setup,monkeypatch):
    c,_,_,_=setup;monkeypatch.setenv('XRPL_NETWORK','mainnet')
    response=c.get('/squads/squad/xrpl',params={'user_id':'a'})
    assert response.status_code==200 and response.json()['status']=='unavailable'


def test_active_but_paused_contract_cannot_receive_collateral(setup):
    c,e,feed,_=setup
    original=feed.event
    def paused(ticker): return [{**row,'market_state':'paused'} for row in original(ticker)]
    feed.event=paused
    assert c.post('/squads/squad/xrpl/lock',json={'user_id':'a'}).status_code==409
    assert not any(call['operation']=='escrow-create' for call in e.calls)
