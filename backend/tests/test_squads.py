from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.database import User, build_engine
from app.squads import register_squads
from app.squad_models import Squad, SquadLeg
from app.xrpl_models import XRPLSettlement
from app import swarm_models


class Feed:
    def __init__(self): self.resolutions = {}; self.price = '.25'; self.closed = False; self.invalid = set()
    def markets(self):
        return [self.market('m1', side) for side in ['yes', 'no']]
    def market(self, symbol, outcome):
        return {'id': symbol, 'event_ticker': symbol.upper(), 'title': 'Will the team win?', 'label': 'Team wins', 'category': 'sports', 'outcome': outcome, 'price': self.price if outcome == 'yes' else '.75', 'closes_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), 'status': 'invalid' if symbol in self.invalid else ('closed' if self.closed else 'active'), 'market_state': 'open', 'resolution': self.resolutions.get(symbol)}
    def event(self, ticker): return [self.market(ticker.lower(), side) for side in ['yes', 'no']]


@pytest.fixture
def setup(tmp_path):
    engine = build_engine('sqlite:///' + str(tmp_path / 'squads.db'))
    with Session(engine) as session:
        session.add_all([User(id=u, name=u.upper(), interests=[], weekly_cap_cents=1000) for u in ['a', 'b', 'c']]); session.commit()
    app = FastAPI(); feed = Feed(); register_squads(app, engine, feed)
    with TestClient(app) as client: yield client, feed, engine


def create(c, members=2):
    response = c.post('/squads', json={'user_id': 'a', 'name': 'Game night', 'stake_cents': 1500, 'member_limit': members, 'lock_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    assert response.status_code == 201, response.text
    return response.json()


def add_leg(c, squad, user='a', market='m1', outcome='yes'):
    response = c.post(f'/squads/{squad}/legs', json={'user_id': user, 'market_id': market, 'outcome': outcome, 'max_price': '.75'})
    assert response.status_code == 200, response.text
    return response.json()

def test_duplicate_market_is_rejected_even_for_the_opposite_side(setup):
    c,_,_=setup;s=create(c)['id']
    c.post('/squads/'+s+'/join',json={'user_id':'b'})
    add_leg(c,s,'a','m1')
    for side in ['yes','no']:
        r=c.post('/squads/'+s+'/legs',json={'user_id':'b','market_id':'m1','outcome':side})
        assert r.status_code==409 and 'already' in r.json()['detail']
    assert len(c.get('/squads/'+s,params={'user_id':'a'}).json()['legs'])==1
    add_leg(c,s,'b','m2')

def test_two_friends_cannot_claim_one_market_at_the_same_time(setup):
    c,_,_=setup;s=create(c)['id']
    c.post('/squads/'+s+'/join',json={'user_id':'b'})
    def choose(user_id):return c.post('/squads/'+s+'/legs',json={'user_id':user_id,'market_id':'m1','outcome':'yes'}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:codes=list(executor.map(choose,['a','b']))
    assert sorted(codes)==[200,409]
    assert len(c.get('/squads/'+s,params={'user_id':'a'}).json()['legs'])==1


def test_opposing_contracts_in_one_matchup_belong_to_the_first_picker(setup):
    c,feed,_=setup;s=create(c)['id']
    c.post('/squads/'+s+'/join',json={'user_id':'b'})
    original=feed.market
    def same_game(symbol,outcome):return {**original(symbol,outcome),'event_ticker':'RAMS-BEARS'}
    feed.market=same_game
    add_leg(c,s,'a','rams','yes')
    for symbol,side in [('rams','no'),('bears','yes'),('bears','no')]:
        r=c.post('/squads/'+s+'/legs',json={'user_id':'b','market_id':symbol,'outcome':side})
        assert r.status_code==409 and 'first' in r.json()['detail']
    data=c.get('/squads/'+s,params={'user_id':'b'}).json()
    assert data['legs'][0]['user_id']=='a' and len(data['legs'])==1


def test_creation_join_capacity_and_isolation(setup):
    c, _, _ = setup; squad = create(c)
    assert squad['members'] == [{'user_id': 'a', 'name': 'A'}]
    assert squad['escrow']['status'] == 'not_configured' and squad['combo']['status'] == 'not_placed'
    assert c.get(f"/squads/{squad['id']}", params={'user_id': 'b'}).status_code == 404
    joined = c.post('/squads/join', json={'user_id': 'b', 'invite_code': squad['invite_code']})
    assert joined.status_code == 200 and len(joined.json()['members']) == 2
    assert c.post(f"/squads/{squad['id']}/join", json={'user_id': 'c'}).status_code == 409
    assert len(c.get('/squads', params={'user_id': 'b'}).json()) == 1
    assert c.get('/squads', params={'user_id': 'c'}).json() == []


def test_swap_retains_history_and_votes_are_unique(setup):
    c, _, engine = setup; squad = create(c)['id']
    c.post(f'/squads/{squad}/join', json={'user_id': 'b'})
    first = add_leg(c, squad)['legs'][0]
    payload = {'user_id': 'b', 'leg_id': first['id'], 'reaction': 'disagree', 'comment': 'Too optimistic'}
    assert c.post(f'/squads/{squad}/votes', json=payload).status_code == 200
    payload['reaction'] = 'agree'
    updated = c.post(f'/squads/{squad}/votes', json=payload).json()['legs'][0]
    assert updated['agree_count'] == 1 and updated['disagree_count'] == 0 and len(updated['votes']) == 1
    changed = add_leg(c, squad, outcome='no')
    assert len(changed['legs']) == 1 and changed['legs'][0]['outcome'] == 'no'
    assert changed['events'][-1]['type'] == 'swap'
    with Session(engine) as session: assert session.query(SquadLeg).count() == 2


def test_lock_requires_full_squad_and_freezes_picks_votes(setup):
    c, _, _ = setup; squad = create(c)['id']
    assert c.post(f'/squads/{squad}/lock', json={'user_id': 'a'}).status_code == 409
    c.post(f'/squads/{squad}/join', json={'user_id': 'b'})
    leg = add_leg(c, squad)['legs'][0]; add_leg(c, squad, 'b', 'm2')
    assert c.post(f'/squads/{squad}/lock', json={'user_id': 'b'}).status_code == 403
    locked = c.post(f'/squads/{squad}/lock', json={'user_id': 'a'})
    assert locked.status_code == 200 and locked.json()['status'] == 'locked'
    assert c.post(f'/squads/{squad}/legs', json={'user_id': 'a', 'market_id': 'm3', 'outcome': 'yes'}).status_code == 409
    assert c.post(f'/squads/{squad}/votes', json={'user_id': 'b', 'leg_id': leg['id'], 'reaction': 'agree'}).status_code == 409
    assert c.post(f'/squads/{squad}/messages', json={'user_id': 'b', 'body': 'Good luck!'}).status_code == 200


def test_deadline_freezes_and_outcome_metrics_are_real(setup):
    c, feed, engine = setup; squad = create(c)['id']; c.post(f'/squads/{squad}/join', json={'user_id': 'b'})
    leg = add_leg(c, squad)['legs'][0]; add_leg(c, squad, 'b', 'm2', 'no')
    c.post(f'/squads/{squad}/votes', json={'user_id': 'b', 'leg_id': leg['id'], 'reaction': 'disagree'})
    with Session(engine) as session: session.get(Squad, squad).lock_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(); session.commit()
    assert c.post(f'/squads/{squad}/legs', json={'user_id': 'a', 'market_id': 'm3', 'outcome': 'yes'}).status_code == 409
    feed.resolutions = {'m1': 'no', 'm2': 'no'}
    response = c.post(f'/squads/{squad}/refresh', json={'user_id': 'a'}); assert response.status_code == 200, response.text
    detail = response.json(); records = {row['user_id']: row['record'] for row in detail['leaderboard']}
    assert detail['status'] == 'resolved' and records['a']['losses'] == 1 and records['b']['wins'] == 1
    assert records['b']['disagree_accuracy'] == 1
    assert detail['payout_plan']['total_payout_cents'] == 1500
    assert [m['payout_cents'] for m in detail['payout_plan']['members']] == [0, 1500]
    again = c.post(f'/squads/{squad}/refresh', json={'user_id': 'b'}).json()
    assert len(again['events']) == len(detail['events'])


def test_closed_price_changed_nonmember_chat_and_markets(setup):
    c, feed, _ = setup; squad = create(c)['id']
    markets = c.get('/squads/markets', params={'user_id': 'a'}).json()
    assert markets[0]['prices'] == {'yes': '0.25', 'no': '0.75'}
    assert c.post(f'/squads/{squad}/messages', json={'user_id': 'b', 'body': 'Intrusion'}).status_code == 404
    assert c.post(f'/squads/{squad}/legs', json={'user_id': 'a', 'market_id': 'm1', 'outcome': 'yes', 'max_price': '.2'}).status_code == 409
    feed.closed = True
    assert c.post(f'/squads/{squad}/legs', json={'user_id': 'a', 'market_id': 'm1', 'outcome': 'yes'}).status_code == 409


def test_validation_rejects_blank_and_naive_times(setup):
    c, _, _ = setup
    payload = {'user_id': 'a', 'name': ' ', 'stake_cents': 1500, 'member_limit': 2, 'lock_at': '2026-10-12T00:00:00'}
    assert c.post('/squads', json=payload).status_code == 422
    squad = create(c)['id']
    assert c.post(f'/squads/{squad}/messages', json={'user_id': 'a', 'body': ' '}).status_code == 422


def test_incomplete_deadline_cannot_settle(setup):
    c, _, engine = setup; squad = create(c)['id']; add_leg(c, squad)
    with Session(engine) as session:
        session.get(Squad, squad).lock_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(); session.commit()
    detail = c.get(f'/squads/{squad}', params={'user_id': 'a'}).json()
    assert detail['status'] == 'incomplete' and detail['payout_plan'] is None
    assert detail['leaderboard'][0]['record']['pending'] == 0
    assert c.post(f'/squads/{squad}/refresh', json={'user_id': 'a'}).status_code == 409
    assert c.post(f'/squads/{squad}/join', json={'user_id': 'b'}).status_code == 409


def test_article_share_vote_is_atomic_and_sources_safe(setup):
    c, _, _ = setup; squad = create(c)['id']; c.post(f'/squads/{squad}/join', json={'user_id': 'b'})
    leg = add_leg(c, squad)['legs'][0]
    payload = {'user_id': 'b', 'title': 'Team update', 'url': 'https://example.com/report', 'summary': 'An update', 'leg_id': leg['id'], 'reaction': 'disagree'}
    response = c.post(f'/squads/{squad}/articles', json=payload)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail['events'][-1]['data']['url'] == payload['url']
    assert detail['legs'][0]['disagree_count'] == 1
    assert c.post(f'/squads/{squad}/articles', json={**payload, 'user_id': 'c'}).status_code == 404
    for url in ['javascript:alert(1)', 'https://user:pass@example.com', 'http://127.0.0.1/report', 'http://localhost/report']:
        assert c.post(f'/squads/{squad}/articles', json={**payload, 'url': url}).status_code == 422
    add_leg(c, squad, 'b', 'm2'); c.post(f'/squads/{squad}/lock', json={'user_id': 'a'})
    assert c.post(f'/squads/{squad}/articles', json=payload).status_code == 409
    assert c.post(f'/squads/{squad}/articles', json={**payload, 'reaction': None}).status_code == 200


def test_invalid_contracts_are_void_not_losses(setup):
    c, feed, _ = setup; squad = create(c)['id']; c.post(f'/squads/{squad}/join', json={'user_id': 'b'})
    add_leg(c, squad); add_leg(c, squad, 'b', 'm2')
    c.post(f'/squads/{squad}/lock', json={'user_id': 'a'})
    feed.invalid = {'m1', 'm2'}
    result = c.post(f'/squads/{squad}/refresh', json={'user_id': 'a'}).json()
    assert result['status'] == 'resolved'
    assert [row['record']['void'] for row in result['leaderboard'] if row.get('kind') != 'swarm'] == [1, 1]
    assert all(row['record']['hit_rate'] is None for row in result['leaderboard'])
    assert [row['payout_cents'] for row in result['payout_plan']['members']] == [750, 750]


def test_concurrent_join_preserves_capacity(setup):
    from concurrent.futures import ThreadPoolExecutor
    c, _, _ = setup; squad = create(c)['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda user: c.post(f'/squads/{squad}/join', json={'user_id': user}), ['b', 'c']))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(c.get(f'/squads/{squad}', params={'user_id': 'a'}).json()['members']) == 2


def test_sse_member_scope_and_cursor(setup):
    import asyncio
    import json
    c, _, _ = setup; squad = create(c)['id']
    first = c.get(f'/squads/{squad}', params={'user_id': 'a'}).json()['events'][-1]['id']
    other = create(c)['id']
    c.post(f'/squads/{other}/messages', json={'user_id': 'a', 'body': 'Other squad secret'})
    sent = c.post(f'/squads/{squad}/messages', json={'user_id': 'a', 'body': 'Visible message'}).json()['events'][-1]
    assert c.get(f'/squads/{squad}/events', params={'user_id': 'b'}).status_code == 404
    endpoint = next(route.endpoint for route in c.app.routes if getattr(route, 'path', '') == '/squads/{squad_id}/events')
    class Connected:
        headers = {}
        async def is_disconnected(self): return False
    async def check():
        response = await endpoint(squad_id=squad, request=Connected(), user_id='a', after=first)
        chunk = await response.body_iterator.__anext__()
        await response.body_iterator.aclose()
        assert f"id: {sent['id']}\n" in chunk and 'event: squad\n' in chunk
        body = json.loads(chunk.split('data: ')[1].strip())
        assert body['body'] == 'Visible message' and body['id'] > first
    asyncio.run(check())


def test_escrow_journal_freezes_all_pick_and_vote_mutations(setup):
    c, _, engine = setup; squad = create(c)['id']; leg = add_leg(c, squad)['legs'][0]
    with Session(engine) as session:
        session.add(XRPLSettlement(squad_id=squad, network='testnet', cancel_after=900000000)); session.commit()
    assert c.post(f'/squads/{squad}/legs', json={'user_id': 'a', 'market_id': 'm2', 'outcome': 'yes'}).status_code == 409
    assert c.post(f'/squads/{squad}/votes', json={'user_id': 'a', 'leg_id': leg['id'], 'reaction': 'agree'}).status_code == 409
    assert c.post(f'/squads/{squad}/join', json={'user_id': 'b'}).status_code == 409
