"""Controlled-worker tests; no model output here is presented as a real forecast."""
import math
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import User, build_engine
from app.swarm import (SwarmService, RunInput, cache_sources, cached_sources, median_probability,
                       register_swarm, refresh_swarm_forecasts, swarm_metrics, validate_estimate)
from app.swarm_models import SwarmRun, SwarmEvent, SwarmEstimate, ResearchSource

AGENTS = ('News Scout', 'Base Rate Analyst', 'Market Reader', 'Skeptic')


class Feed:
    def market(self, market_id, outcome):
        return {'id': market_id, 'event_ticker': market_id, 'title': 'Controlled future market', 'label': 'Yes proposition',
                'category': 'Weather', 'outcome': outcome, 'price': '.4' if outcome == 'yes' else '.7',
                'closes_at': (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                'status': 'active', 'market_state': 'open', 'terms_url': 'https://venue.example/rules'}

    def event(self, ticker):
        return [{**self.market(ticker, 'yes'), 'status': 'settled', 'resolution': 'yes'}]


def completed_worker(payload):
    yield {'type': 'source_found', 'data': {'agent': 'News Scout', 'url': 'https://source.example/article', 'title': 'Controlled article', 'snippet': 'Controlled evidence'}}
    for round_number in (1, 2):
        if round_number == 2:
            yield {'type': 'round_changed', 'data': {'round': 2}}
        for index, agent in enumerate(AGENTS):
            yield {'type': 'agent_started', 'data': {'agent': agent, 'round': round_number}}
            yield {'type': 'estimate_submitted' if round_number == 1 else 'estimate_revised', 'data': {
                'agent': agent, 'round': round_number, 'probability': [.2, .4, .6, .8][index], 'confidence': 'medium',
                'reasons': ['First public reason', 'Second public reason', 'Third public reason'], 'sources': ['https://source.example/article'],
                **({'revision_reason': 'Controlled revision explanation'} if round_number == 2 else {})}}
    yield {'type': 'usage', 'data': {'input_tokens': 90, 'output_tokens': 45, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0, 'web_search_requests': 1, 'model_calls': 9}}
    yield {'type': 'final_result', 'data': {'probability': .5, 'market_price': 999, 'gap': 999, 'summary': 'Controlled summary',
                                           'reasons': ['A', 'B', 'C'], 'disagreements': 'Controlled disagreement'}}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'controlled-provider-key')
    monkeypatch.delenv('CONTEXT_DEV_API_KEY', raising=False)
    engine = build_engine('sqlite:///' + str(tmp_path / 'swarm.db'))
    with Session(engine) as session:
        session.add_all([User(id='alice', name='Alice', interests=['weather'], weekly_cap_cents=500), User(id='bob', name='Bob', interests=['sports'], weekly_cap_cents=500), User(id='cara', name='Cara', interests=[], weekly_cap_cents=500)])
        session.commit()
    app = FastAPI()
    service = register_swarm(app, engine, Feed(), None, completed_worker)
    return app, service, engine


def wait(service, run_id):
    for _ in range(300):
        result = service.read(run_id, 'alice')
        if result['status'] in ('completed', 'failed'):
            return result
        time.sleep(.01)
    pytest.fail('Controlled worker did not terminate')


def test_missing_key_returns_503_without_job_progress(setup, monkeypatch):
    app, service, engine = setup
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    with TestClient(app) as client:
        response = client.post('/swarm/run', json={'user_id': 'alice', 'market_id': 'market-a', 'outcome': 'yes'})
        assert response.status_code == 503 and 'ANTHROPIC_API_KEY' in response.json()['detail']
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SwarmRun)) == 0
        assert session.scalar(select(func.count()).select_from(SwarmEvent)) == 0


def test_completed_run_uses_real_recorded_quote_and_code_median(setup):
    app, service, engine = setup
    response = TestClient(app).post('/swarm/run', json={'user_id': 'alice', 'market_id': 'market-a', 'outcome': 'no'})
    assert response.status_code == 200
    result = wait(service, response.json()['id'])
    assert result['status'] == 'completed', result
    assert result['result']['probability'] == .5
    assert result['result']['market_price'] == .7
    assert result['result']['gap'] == pytest.approx(-.2)
    assert len(result['estimates']) == 8
    assert result['usage']['model_calls'] == 9 and result['usage']['web_search_requests'] == 1


def test_completed_exact_market_cache_does_not_start_new_worker(setup):
    app, service, engine = setup
    first = service.start(RunInput(user_id='alice', market_id='market-a', outcome='yes'))
    assert wait(service, first['id'])['status'] == 'completed'
    second = service.start(RunInput(user_id='alice', market_id='market-a', outcome='yes'))
    assert second['id'] == first['id'] and second['cached']
    third = service.start(RunInput(user_id='alice', market_id='market-a', outcome='no'))
    assert third['id'] != first['id']
    wait(service, third['id'])


def test_account_isolation_for_read_stream_and_latest(setup):
    app, service, engine = setup
    run_id = service.start(RunInput(user_id='alice', market_id='market-a'))['id']
    wait(service, run_id)
    client = TestClient(app)
    assert client.get('/swarm/runs/' + run_id, params={'user_id': 'bob'}).status_code == 404
    assert client.get('/swarm/runs/' + run_id + '/stream', params={'user_id': 'bob'}).status_code == 404
    assert client.get('/swarm/markets/market-a', params={'user_id': 'bob'}).json() == {'run': None}
    assert client.get('/swarm/markets/market-a', params={'user_id': 'alice'}).json()['run']['id'] == run_id


def test_sse_replays_persisted_ids_and_respects_after_cursor(setup):
    app, service, engine = setup
    run_id = service.start(RunInput(user_id='alice', market_id='market-a'))['id']
    result = wait(service, run_id)
    cursor = result['events'][2]['id']
    client = TestClient(app)
    response = client.get('/swarm/runs/' + run_id + '/stream', params={'user_id': 'alice', 'after': cursor})
    assert response.status_code == 200 and 'text/event-stream' in response.headers['content-type']
    ids = [int(line[4:]) for line in response.text.splitlines() if line.startswith('id: ')]
    assert ids == [event['id'] for event in result['events'] if event['id'] > cursor]
    assert 'event: final_result' in response.text
    assert client.get('/swarm/runs/' + run_id + '/stream', params={'user_id': 'alice'}, headers={'Last-Event-ID': 'bad'}).status_code == 400


def test_user_hourly_limit_includes_failed_provider_attempts(setup):
    app, service, engine = setup
    service.worker = lambda payload: iter([{'type': 'error', 'data': {'message': 'Controlled provider error'}}])
    for market_id in ('market-a', 'market-b'):
        assert wait(service, service.start(RunInput(user_id='alice', market_id=market_id))['id'])['status'] == 'failed'
    response = TestClient(app).post('/swarm/run', json={'user_id': 'alice', 'market_id': 'market-c'})
    assert response.status_code == 429


def test_atomic_active_dedup_and_global_concurrency(setup):
    app, service, engine = setup
    release = threading.Event()
    def blocked(payload):
        release.wait(2)
        yield {'type': 'error', 'data': {'message': 'Controlled end'}}
    service.worker = blocked
    try:
        one = service.start(RunInput(user_id='alice', market_id='market-a'))
        duplicate = service.start(RunInput(user_id='alice', market_id='market-a'))
        assert duplicate['id'] == one['id'] and duplicate['cached']
        two = service.start(RunInput(user_id='bob', market_id='market-b'))
        response = TestClient(app).post('/swarm/run', json={'user_id': 'cara', 'market_id': 'market-c'})
        assert response.status_code == 429
    finally:
        release.set()
    wait(service, one['id'])
    for _ in range(100):
        if service.read(two['id'], 'bob')['status'] == 'failed':
            break
        time.sleep(.01)


@pytest.mark.parametrize('values', [[.1,.9,.2,.3], [.8,.4,.6,.2]])
def test_four_agent_median_is_middle_pair_mean(values):
    ordered = sorted(values)
    assert median_probability(values) == pytest.approx((ordered[1] + ordered[2]) / 2)


@pytest.mark.parametrize('values', [[.1,.2,.3], [.1,.2,.3,math.nan], [.1,.2,.3,True], [-.1,.2,.3,.4]])
def test_median_rejects_missing_or_invalid_estimate(values):
    with pytest.raises(ValueError):
        median_probability(values)


@pytest.mark.parametrize('field,value', [('probability', math.nan), ('probability', True), ('probability', 1.1), ('confidence','certain'), ('reasons',['one']), ('sources',['javascript:alert(1)'])])
def test_schema_rejects_invalid_agent_output(field, value):
    data = {'agent': 'Skeptic', 'round': 1, 'probability': .4, 'confidence': 'low', 'reasons': ['a','b','c'], 'sources': []}
    with pytest.raises(ValueError):
        validate_estimate({**data, field:value})


def test_incomplete_worker_and_wrong_median_never_produce_forecast(setup):
    app, service, engine = setup
    service.worker = lambda payload: iter([{'type':'agent_started','data':{'agent':'Skeptic','round':1}}])
    result = wait(service, service.start(RunInput(user_id='alice', market_id='market-a'))['id'])
    assert result['status'] == 'failed' and result['result'] is None
    def wrong(payload):
        for packet in completed_worker(payload):
            if packet['type'] == 'final_result':
                packet['data']['probability'] = .99
            yield packet
    service.worker = wrong
    result = wait(service, service.start(RunInput(user_id='alice', market_id='market-b'))['id'])
    assert result['status'] == 'failed' and result['result'] is None


def test_cache_reuses_safe_public_sources_and_expires(setup):
    app, service, engine = setup
    cache_sources(engine, 'market-a', [{'url':'https://source.example/a','title':'Real metadata','snippet':'Evidence'}, {'url':'javascript:bad','title':'Unsafe'}], 'Context.dev')
    assert len(cached_sources(engine, 'market-a')) == 1
    cache_sources(engine, 'market-a', [{'url':'https://source.example/a','title':'New metadata','snippet':''}], 'Anthropic web search')
    assert cached_sources(engine, 'market-a')[0]['snippet'] == 'Evidence'
    with Session(engine) as session:
        source = session.scalar(select(ResearchSource))
        source.fetched_at = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
        session.commit()
    assert cached_sources(engine, 'market-a') == []


def test_completed_forecasts_score_once_and_voids_are_separate(setup):
    app, service, engine = setup
    result = wait(service, service.start(RunInput(user_id='alice', market_id='market-a'))['id'])
    assert result['status'] == 'completed'
    assert refresh_swarm_forecasts(engine, Feed()) == 1
    assert refresh_swarm_forecasts(engine, Feed()) == 0
    metrics = swarm_metrics(engine, 'alice')
    assert metrics['brier_score'] == .25 and metrics['edge_score'] == pytest.approx(.6)
    run_id = service.start(RunInput(user_id='alice', market_id='market-b'))['id']
    wait(service, run_id)
    class VoidFeed(Feed):
        def event(self, ticker):
            return [{**self.market(ticker, 'yes'), 'status':'invalid', 'resolution':None}]
    assert refresh_swarm_forecasts(engine, VoidFeed()) == 1
    metrics = swarm_metrics(engine, 'alice')
    assert metrics['void_count'] == 1 and metrics['resolved_count'] == 1 and metrics['brier_score'] == .25


def test_restart_marks_interrupted_runs_failed(setup):
    app, service, engine = setup
    with Session(engine) as session:
        session.add(SwarmRun(id='interrupted', user_id='alice', market_id='market-a', outcome='yes', model='controlled', status='running', market=Feed().market('market-a','yes'), usage={}))
        session.commit()
    service.recover_interrupted()
    result = service.read('interrupted', 'alice')
    assert result['status'] == 'failed' and result['result'] is None
    assert result['events'][0]['type'] == 'error'


def test_wrong_or_expired_market_never_creates_run(setup):
    app, service, engine = setup
    class WrongFeed(Feed):
        def market(self, market_id, outcome):
            return {**super().market(market_id, outcome), 'id':'wrong-market'}
    service.feed = WrongFeed()
    assert TestClient(app).post('/swarm/run', json={'user_id':'alice','market_id':'market-a'}).status_code == 503
    class ExpiredFeed(Feed):
        def market(self, market_id, outcome):
            return {**super().market(market_id, outcome), 'closes_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
    service.feed = ExpiredFeed()
    assert TestClient(app).post('/swarm/run', json={'user_id':'alice','market_id':'market-a'}).status_code == 409
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SwarmRun)) == 0


def test_search_limits_and_round_boundary_are_enforced(setup):
    app, service, engine = setup
    def excessive(payload):
        yield {'type':'agent_started','data':{'agent':'News Scout','round':1}}
        for index in range(3):
            yield {'type':'search_query','data':{'agent':'News Scout','query':str(index)}}
    service.worker = excessive
    result = wait(service, service.start(RunInput(user_id='alice',market_id='market-a'))['id'])
    assert result['status'] == 'failed'
    assert len([e for e in result['events'] if e['type']=='search_query']) == 2
    def late(payload):
        yield {'type':'agent_started','data':{'agent':'Skeptic','round':2}}
        yield {'type':'search_query','data':{'agent':'Skeptic','query':'Too late'}}
    service.worker = late
    result = wait(service, service.start(RunInput(user_id='alice',market_id='market-b'))['id'])
    assert result['status'] == 'failed'
    assert not [e for e in result['events'] if e['type']=='search_query']


def test_missing_context_key_does_not_call_reading_provider(setup):
    app, service, engine = setup
    class Reading:
        def materials(self, *args):
            pytest.fail('No Context request is permitted without its configured key')
    service.reading = Reading()
    result = wait(service, service.start(RunInput(user_id='alice',market_id='market-a'))['id'])
    assert result['status'] == 'completed'


def test_sources_from_shared_cache_are_passed_to_worker_without_new_context_call(setup, monkeypatch):
    app, service, engine = setup
    monkeypatch.setenv('CONTEXT_DEV_API_KEY','controlled-context-key')
    cache_sources(engine, 'market-a', [{'url':'https://cached.example/a','title':'Cached public material','snippet':'Observed excerpt'}], 'Context.dev')
    class Reading:
        def materials(self,*args):
            pytest.fail('Existing shared evidence must avoid a new Context request')
    service.reading = Reading()
    observed = []
    def worker(payload):
        observed.extend(payload['sources'])
        yield from completed_worker(payload)
    service.worker = worker
    result = wait(service,service.start(RunInput(user_id='alice',market_id='market-a'))['id'])
    assert result['status'] == 'completed'
    assert observed[0]['url'] == 'https://cached.example/a'
