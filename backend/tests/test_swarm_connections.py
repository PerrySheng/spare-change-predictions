"""Controlled integration checks; these never stand in for live Claude research."""
from datetime import datetime, timedelta, timezone
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.database import User, build_engine, timestamp
from app.squad_models import Squad, SquadMember, SquadLeg, SquadEvent
from app.swarm_models import SwarmRun, SwarmShare
from app.swarm import register_swarm
from app.squads import register_squads
from app.swarm_connections import register_swarm_connections, squad_swarm_record, comparison, post_ready_shares
from test_swarm import completed_worker, Feed


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'controlled-test-key')
    monkeypatch.delenv('CONTEXT_DEV_API_KEY', raising=False)
    engine = build_engine('sqlite:///' + str(tmp_path / 'connections.db'))
    now = datetime.now(timezone.utc)
    with Session(engine) as s:
        s.add_all([User(id=u, name=u, interests=[], weekly_cap_cents=1000) for u in ['a', 'b', 'outsider']]); s.flush()
        s.add(Squad(id='s', creator_id='a', name='Squad', invite_code='CODE', stake_cents=1500, member_limit=2, status='locked', lock_at=now.isoformat(), locked_at=now.isoformat())); s.flush()
        s.add_all([SquadMember(squad_id='s', user_id=u) for u in ['a', 'b']])
        s.add(SquadLeg(id='leg', squad_id='s', user_id='a', market_id='market-a', event_ticker='EVENT', title='Controlled event', label='Outcome', category='weather', outcome='yes', entry_price='.3', closes_at=(now+timedelta(days=1)).isoformat(), locked=True, active=True, status='won', resolved_at=timestamp()))
        s.commit()
    app = FastAPI(); feed = Feed()
    service = register_swarm(app, engine, feed, None, completed_worker)
    register_squads(app, engine, feed)
    register_swarm_connections(app, engine)
    return TestClient(app), engine, service


def forecast(engine, id='r', **changes):
    now = datetime.now(timezone.utc)
    values = dict(id=id, user_id='a', market_id='market-a', outcome='yes', model='controlled', status='completed', created_at=(now-timedelta(minutes=4)).isoformat(), completed_at=(now-timedelta(minutes=3)).isoformat(),
                  market={'id':'market-a', 'event_ticker':'EVENT', 'title':'Controlled event', 'category':'weather', 'closes_at':(now+timedelta(days=1)).isoformat(), 'outcome':'yes', 'price':'.3', 'yes_price':'.3', 'no_price':'.8'},
                  result={'probability':.4, 'selected_probability':.4, 'market_price':.3, 'gap':.1, 'summary':'Controlled research', 'sources':[], 'reasons':['A','B','C'], 'disagreements':'Different views'}, resolution='yes', brier_score=.36, side_edge=-.8, scored_at=timestamp(), usage={})
    values.update(changes)
    with Session(engine) as s: s.add(SwarmRun(**values)); s.commit()


def test_canonical_forecast_is_earliest_before_lock_not_best_or_latest(setup):
    c, engine, _ = setup
    forecast(engine)
    forecast(engine, 'later', completed_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(), result={'probability':.9}, side_edge=.7)
    assert c.post('/squads/s/swarm/share', json={'user_id':'a','leg_id':'leg','run_id':'r'}).status_code==200
    with Session(engine) as s:
        record = squad_swarm_record(s, s.get(Squad, 's'))
        assert record['losses'] == 1 and record['edge_score'] == pytest.approx(-.8)
        comp = comparison(s, s.get(Squad, 's'), 'a')
        assert comp['matched_count'] == 1 and comp['friend_edge'] == pytest.approx(.7)
        assert comp['swarm_edge'] == pytest.approx(-.8) and comp['markets'][0]['run_id'] == 'r'


def test_unshared_run_details_never_leak_through_profile_comparisons(setup):
    c, engine, _ = setup; forecast(engine)
    data=c.get('/squads/s', params={'user_id':'b'}).json()
    alice=next(row for row in data['leaderboard'] if row['user_id']=='a')
    assert alice['record']['swarm_comparison']['markets']==[]
    assert alice['record']['swarm_comparison']['matched_count']==0
    assert c.get('/swarm/runs/r', params={'user_id':'b'}).status_code==404
    assert c.get('/squads/s/swarm/runs/r', params={'user_id':'b'}).status_code==404


def test_selectively_sharing_a_later_run_cannot_replace_the_canonical_run(setup):
    _, engine, _ = setup; forecast(engine)
    forecast(engine, 'later', completed_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())
    with Session(engine) as s:
        s.add(SwarmShare(squad_id='s', leg_id='leg', run_id='later', user_id='a', status='posted'));s.commit()
        assert comparison(s,s.get(Squad,'s'),'a')['matched_count']==0
        s.add(SwarmShare(squad_id='s', leg_id='leg', run_id='r', user_id='a', status='posted'));s.commit()
        assert comparison(s,s.get(Squad,'s'),'a')['markets'][0]['run_id']=='r'


def test_late_private_unpriced_and_duplicate_forecasts_do_not_inflate_scores(setup):
    _, engine, _ = setup
    forecast(engine, user_id='outsider')
    forecast(engine, 'late', completed_at=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat())
    with Session(engine) as s: assert squad_swarm_record(s, s.get(Squad,'s'))['resolved'] == 0
    forecast(engine, 'unpriced', market={'closes_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(), 'yes_price':'.3'})
    with Session(engine) as s:
        record = squad_swarm_record(s, s.get(Squad,'s'))
        assert record['edge_score'] is None and record['unpriced_count'] == 1
        assert comparison(s, s.get(Squad,'s'),'a')['matched_count'] == 0


def test_share_is_exact_leg_owned_completed_and_idempotent(setup):
    c, engine, _ = setup; forecast(engine)
    path = '/squads/s/swarm/share'
    payload = {'user_id':'a', 'leg_id':'leg', 'run_id':'r'}
    assert c.post(path, json={**payload,'user_id':'outsider'}).status_code == 404
    assert c.post(path, json={**payload,'user_id':'b'}).status_code == 404
    assert c.post(path, json=payload).json()['status'] == 'posted'
    assert c.post(path, json=payload).json()['status'] == 'posted'
    detail = c.get('/squads/s', params={'user_id':'b'}).json()
    messages = [e for e in detail['messages'] if e['type']=='swarm_forecast']
    assert len(messages)==1 and messages[0]['leg_id']=='leg'
    assert messages[0]['data']['probability']==.4 and messages[0]['body']=='Controlled research'
    assert c.get('/squads/s/swarm/runs/r', params={'user_id':'b'}).status_code==200
    assert c.get('/squads/s/swarm/runs/r', params={'user_id':'outsider'}).status_code==404
    assert c.get('/swarm/runs/r', params={'user_id':'b'}).status_code==404


def test_mismatched_and_unshared_runs_are_rejected(setup):
    c, engine, _ = setup; forecast(engine, market_id='different')
    assert c.post('/squads/s/swarm/share', json={'user_id':'a','leg_id':'leg','run_id':'r'}).status_code==409
    assert c.get('/squads/s/swarm/runs/r', params={'user_id':'b'}).status_code==404


def test_ask_persists_intent_and_posts_after_real_worker_finishes(setup):
    c, engine, service = setup
    response = c.post('/squads/s/swarm/ask', json={'user_id':'a','leg_id':'leg'})
    assert response.status_code==200, response.text
    run_id=response.json()['run_id']
    for _ in range(300):
        with Session(engine) as s:
            count=s.scalar(select(func.count()).select_from(SquadEvent).where(SquadEvent.type=='swarm_forecast'))
        if count: break
        time.sleep(.01)
    assert count==1
    assert c.get('/squads/s/swarm/runs/'+run_id, params={'user_id':'b'}).json()['status']=='completed'


def test_cached_ask_needs_no_provider_key_or_new_call(setup, monkeypatch):
    c, engine, _ = setup; forecast(engine)
    monkeypatch.delenv('ANTHROPIC_API_KEY')
    for _ in range(2):
        response=c.post('/squads/s/swarm/ask', json={'user_id':'a','leg_id':'leg'})
        assert response.status_code==200 and response.json()['status']=='posted'
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(SwarmRun))==1
        assert s.scalar(select(func.count()).select_from(SquadEvent))==1


def test_pending_failed_run_posts_only_an_error_once(setup):
    _, engine, _ = setup; forecast(engine, status='failed', result=None, error='Controlled provider failure')
    with Session(engine) as s:
        s.add(SwarmShare(squad_id='s', leg_id='leg', run_id='r', user_id='a')); s.commit()
    post_ready_shares(engine, 'r'); post_ready_shares(engine, 'r')
    with Session(engine) as s:
        events=s.scalars(select(SquadEvent)).all()
        assert len(events)==1 and events[0].type=='swarm_error'
        assert 'Controlled provider failure' in events[0].body
        assert 'probability' not in events[0].data


def test_concurrent_share_requests_post_once(setup):
    from concurrent.futures import ThreadPoolExecutor
    c, engine, _ = setup; forecast(engine)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _:c.post('/squads/s/swarm/share', json={'user_id':'a','leg_id':'leg','run_id':'r'}), range(8)))
    assert all(r.status_code==200 for r in responses)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(SwarmShare))==1
        assert s.scalar(select(func.count()).select_from(SquadEvent))==1


def test_voids_stay_separate_and_swapped_picks_do_not_score(setup):
    _, engine, _ = setup; forecast(engine, resolution='void', brier_score=None, side_edge=None)
    with Session(engine) as s:
        assert squad_swarm_record(s,s.get(Squad,'s'))['void']==1
        assert comparison(s,s.get(Squad,'s'),'a')['matched_count']==0
        s.get(SquadLeg,'leg').active=False;s.commit()
        assert squad_swarm_record(s,s.get(Squad,'s'))['forecast_count']==0


def test_no_key_creates_no_chat_or_fake_forecast(setup, monkeypatch):
    c, engine, _ = setup; monkeypatch.delenv('ANTHROPIC_API_KEY')
    assert c.post('/squads/s/swarm/ask', json={'user_id':'a','leg_id':'leg'}).status_code==503
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(SwarmRun))==0
        assert s.scalar(select(func.count()).select_from(SquadEvent))==0
