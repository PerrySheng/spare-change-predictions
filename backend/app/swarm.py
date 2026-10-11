"""Bounded, persisted Claude research jobs. No synthetic forecasts or progress."""
import asyncio
import json
import math
import os
import shutil
import subprocess
import threading
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Literal

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .context_reading import _safe_url
from .database import User, timestamp, uid
from .providers import ProviderError
from .swarm_models import SwarmRun, SwarmEvent, SwarmEstimate, MarketSnapshot, ResearchSource

AGENTS = ('News Scout', 'Base Rate Analyst', 'Market Reader', 'Skeptic')
ACTIVE = ('queued', 'running')
TERMINAL = ('completed', 'failed')
CACHE_MINUTES = 30
WORKER_FILE = Path(__file__).resolve().parents[2] / 'swarm' / 'dist' / 'worker.js'


@contextmanager
def transaction(engine):
    with Session(engine) as session:
        try:
            session.execute(text('BEGIN IMMEDIATE'))
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _source(row):
    if not isinstance(row, dict) or not _safe_url(row.get('url')):
        return None
    title = row.get('title') or row['url']
    snippet = row.get('snippet') or ''
    return {'url': row['url'], 'title': str(title)[:200], 'snippet': str(snippet)[:500]}


def cache_sources(engine, market_id, sources, provider):
    """Persist only public source metadata; no network call or customer inputs."""
    normalized = {}
    for row in sources[:30] if isinstance(sources, list) else []:
        source = _source(row)
        if source:
            normalized[source['url']] = source
    with transaction(engine) as session:
        for source in normalized.values():
            saved = session.scalar(select(ResearchSource).where(ResearchSource.market_id == market_id, ResearchSource.url == source['url']))
            if saved is None:
                saved = ResearchSource(market_id=market_id, url=source['url'], title=source['title'], snippet=source['snippet'], provider=str(provider)[:80])
                session.add(saved)
            else:
                saved.title = source['title']
                # A citation can add its observed excerpt to a previously bare search result.
                if source['snippet']:
                    saved.snippet = source['snippet']
                saved.provider = str(provider)[:80]
                saved.fetched_at = timestamp()
    return list(normalized.values())


def cached_sources(engine, market_id):
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=CACHE_MINUTES)).isoformat()
    with Session(engine) as session:
        rows = session.scalars(select(ResearchSource).where(ResearchSource.market_id == market_id, ResearchSource.fetched_at >= cutoff).order_by(ResearchSource.fetched_at.desc()).limit(15)).all()
        return [{'url': row.url, 'title': row.title, 'snippet': row.snippet, 'provider': row.provider, 'fetched_at': row.fetched_at} for row in rows]


def validate_estimate(data, revised=False):
    if not isinstance(data, dict) or data.get('agent') not in AGENTS:
        raise ValueError('Unknown research agent.')
    probability = data.get('probability')
    if isinstance(probability, bool) or not isinstance(probability, (float, int)) or not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError('Agent probability must be a finite number in 0–1.')
    if data.get('confidence') not in ('low', 'medium', 'high'):
        raise ValueError('Agent confidence is invalid.')
    reasons = data.get('reasons')
    if not isinstance(reasons, list) or len(reasons) != 3 or any(not isinstance(r, str) or not r.strip() or len(r) > 500 for r in reasons):
        raise ValueError('Each estimate needs exactly three short reasons.')
    sources = data.get('sources')
    if not isinstance(sources, list) or len(sources) > 15 or any(not _safe_url(s) for s in sources):
        raise ValueError('Agent sources must be safe public source URLs.')
    expected_round = 2 if revised else 1
    if data.get('round') != expected_round:
        raise ValueError('Estimate arrived in an invalid research round.')
    if revised and (not isinstance(data.get('revision_reason'), str) or not data['revision_reason'].strip() or len(data['revision_reason']) > 700):
        raise ValueError('A revised estimate needs a brief explanation.')
    return data


def median_probability(values):
    if len(values) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError('Exactly four valid revised estimates are required.')
    return median(values)


def _event_json(row):
    return {'id': row.id, 'type': row.type, 'data': row.data, 'created_at': row.created_at}


def _estimate_json(row):
    return {key: getattr(row, key) for key in ('agent', 'round', 'probability', 'confidence', 'reasons', 'sources', 'revision_reason', 'created_at')}


def _run_json(row):
    return {'id': row.id, 'run_id': row.id, 'user_id': row.user_id, 'market_id': row.market_id, 'outcome': row.outcome,
            'model': row.model, 'status': row.status, 'market': row.market, 'result': row.result, 'usage': row.usage,
            'error': row.error, 'created_at': row.created_at, 'completed_at': row.completed_at,
            'resolution': row.resolution, 'brier_score': row.brier_score, 'side_edge': row.side_edge}


def _user(session, user_id):
    if not session.get(User, user_id):
        raise HTTPException(404, 'User not found. Start with onboarding.')


def _owned_run(session, run_id, user_id):
    _user(session, user_id)
    run = session.get(SwarmRun, run_id)
    if run is None or run.user_id != user_id:
        raise HTTPException(404, 'Research run not found for this user.')
    return run


def node_worker(payload, stop_event=None):
    """Yield bounded JSON lines from one real official-SDK worker process."""
    node = os.getenv('SWARM_NODE_BIN') or shutil.which('node')
    if not node or not WORKER_FILE.is_file():
        raise RuntimeError('Research worker is not built. Run npm ci && npm run build in swarm/, and install Node.js.')
    process = subprocess.Popen([node, str(WORKER_FILE)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1, cwd=str(WORKER_FILE.parent.parent))
    watchdog = threading.Timer(600, process.kill)
    watchdog.daemon = True
    watchdog.start()
    finished = threading.Event()
    def cancel_on_shutdown():
        while not finished.wait(.2):
            if stop_event is not None and stop_event.is_set():
                if process.poll() is None:
                    process.terminate()
                return
    canceller = threading.Thread(target=cancel_on_shutdown, daemon=True)
    if stop_event is not None:
        canceller.start()
    try:
        process.stdin.write(json.dumps(payload) + '\n')
        process.stdin.close()
        for line in process.stdout:
            if len(line) > 65536:
                raise RuntimeError('Research worker emitted an oversized event.')
            try:
                packet = json.loads(line)
            except ValueError:
                raise RuntimeError('Research worker returned an incomplete event. No forecast was manufactured.') from None
            yield packet
        if process.wait(timeout=5) != 0:
            raise RuntimeError('The research worker stopped before completing the forecast.')
    finally:
        finished.set()
        watchdog.cancel()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        if process.stdout:
            process.stdout.close()


class RunInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    market_id: str = Field(min_length=1, max_length=160)
    outcome: Literal['yes', 'no'] = 'yes'


class SwarmService:
    def __init__(self, engine, feed, reading, worker=node_worker):
        self.engine, self.feed, self.reading, self.worker = engine, feed, reading, worker
        self._threads = set()
        self._thread_lock = threading.Lock()
        self._stop = threading.Event()

    def recover_interrupted(self):
        with transaction(self.engine) as session:
            for run in session.scalars(select(SwarmRun).where(SwarmRun.status.in_(ACTIVE))).all():
                run.status, run.completed_at, run.error = 'failed', timestamp(), 'Research was interrupted by a server restart. No completed forecast is available.'
                session.add(SwarmEvent(run_id=run.id, type='error', data={'message': run.error}))

    def start(self, request):
        # Missing credentials or unavailable worker must not create progress.
        if not (os.getenv('ANTHROPIC_API_KEY') or '').strip():
            raise HTTPException(503, 'Set ANTHROPIC_API_KEY in the server .env and restart the backend to run the research swarm.')
        if self.worker is node_worker and (not WORKER_FILE.is_file() or not (os.getenv('SWARM_NODE_BIN') or shutil.which('node'))):
            raise HTTPException(503, 'Build the research worker with npm ci && npm run build in swarm/, then restart the backend.')
        with Session(self.engine) as session:
            _user(session, request.user_id)
        try:
            market = dict(self.feed.market(request.market_id, request.outcome))
        except ProviderError as exc:
            raise HTTPException(503, str(exc)) from exc
        if market.get('id') != request.market_id or market.get('outcome') != request.outcome:
            raise HTTPException(503, 'Gemini returned a different contract or side. No research run was created.')
        if market.get('status') != 'active' or market.get('market_state') not in (None, 'open'):
            raise HTTPException(409, 'Research requires a currently open Gemini contract.')
        try:
            closes_at = datetime.fromisoformat(market['closes_at'].replace('Z', '+00:00'))
            if closes_at.tzinfo is None or closes_at <= datetime.now(timezone.utc):
                raise ValueError
            price = float(market['price'])
            if not math.isfinite(price) or not 0 < price < 1:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise HTTPException(409, 'This market is expired or its executable quote is unavailable.') from None
        # Preserve both fresh side quotes if the venue actually supplies them.
        market[request.outcome + '_price'] = market['price']
        other = 'no' if request.outcome == 'yes' else 'yes'
        try:
            counterpart = self.feed.market(request.market_id, other)
            market[other + '_price'] = counterpart.get('price') if counterpart.get('id') == request.market_id and counterpart.get('outcome') == other else None
        except ProviderError:
            market[other + '_price'] = None
        market['observed_at'] = timestamp()
        now = datetime.now(timezone.utc)
        with transaction(self.engine) as session:
            _user(session, request.user_id)
            exact = [SwarmRun.user_id == request.user_id, SwarmRun.market_id == request.market_id, SwarmRun.outcome == request.outcome]
            existing = session.scalar(select(SwarmRun).where(*exact, SwarmRun.status.in_(ACTIVE)).order_by(SwarmRun.created_at.desc()))
            if existing:
                return {'id': existing.id, 'run_id': existing.id, 'status': existing.status, 'cached': True}
            cached = session.scalar(select(SwarmRun).where(*exact, SwarmRun.status == 'completed', SwarmRun.completed_at >= (now - timedelta(minutes=CACHE_MINUTES)).isoformat()).order_by(SwarmRun.completed_at.desc()))
            if cached:
                return {'id': cached.id, 'run_id': cached.id, 'status': cached.status, 'cached': True}
            recent_count = session.scalar(select(func.count()).select_from(SwarmRun).where(SwarmRun.user_id == request.user_id, SwarmRun.created_at >= (now - timedelta(hours=1)).isoformat()))
            if recent_count >= 2:
                raise HTTPException(429, 'Research is limited to two new runs per user per hour. Open a cached result or try later.')
            active_count = session.scalar(select(func.count()).select_from(SwarmRun).where(SwarmRun.status.in_(ACTIVE)))
            if active_count >= 2:
                raise HTTPException(429, 'Two research runs are already active. Try again after one finishes.')
            run = SwarmRun(id=uid(), user_id=request.user_id, market_id=request.market_id, outcome=request.outcome, model=os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-5-5'), status='queued', market=market, usage={})
            session.add(run)
            session.flush()
            session.add(MarketSnapshot(market_id=request.market_id, run_id=run.id, data=market))
            run_id = run.id
        thread = threading.Thread(target=self._execute, args=(run_id,), name='swarm-' + run_id[:8], daemon=True)
        with self._thread_lock:
            self._threads.add(thread)
        try:
            thread.start()
        except RuntimeError:
            with self._thread_lock:
                self._threads.discard(thread)
            self._fail(run_id, 'Research worker could not start. Try again after checking server resources.')
            raise HTTPException(503, 'Research worker could not start. Check server resources.') from None
        return {'id': run_id, 'run_id': run_id, 'status': 'queued', 'cached': False}

    def _fail(self, run_id, message):
        with transaction(self.engine) as session:
            run = session.get(SwarmRun, run_id)
            if run is None or run.status in TERMINAL:
                return
            run.status, run.error, run.completed_at = 'failed', str(message)[:1000], timestamp()
            session.add(SwarmEvent(run_id=run_id, type='error', data={'message': run.error}))

    def _execute(self, run_id):
        try:
            with transaction(self.engine) as session:
                run = session.get(SwarmRun, run_id)
                if run.status not in ACTIVE:
                    return
                run.status = 'running'
                payload = {'market': run.market, 'outcome': run.outcome, 'model': run.model, 'sources': []}
                market_id = run.market_id
            sources = cached_sources(self.engine, market_id)
            if not sources and os.getenv('CONTEXT_DEV_API_KEY') and self.reading:
                try:
                    materials = self.reading.materials(payload['market']['title'], payload['market'].get('label', ''))
                    sources = cache_sources(self.engine, market_id, materials.get('sources', []), 'Context.dev')
                except ProviderError:
                    sources = []
            payload['sources'] = sources
            iterator = iter(node_worker(payload, self._stop) if self.worker is node_worker else self.worker(payload))
            try:
                for packet in iterator:
                    if self._stop.is_set():
                        raise RuntimeError('Research was interrupted by server shutdown.')
                    self._packet(run_id, packet)
            finally:
                close = getattr(iterator, 'close', None)
                if close:
                    close()
            with Session(self.engine) as session:
                run = session.get(SwarmRun, run_id)
                if run.status not in TERMINAL:
                    raise RuntimeError('Research ended without a complete forecast. No result was manufactured.')
        except Exception as exc:
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Research failed. Check provider access and worker configuration.'
            self._fail(run_id, message)
        finally:
            from .swarm_connections import post_ready_shares
            try:
                post_ready_shares(self.engine, run_id)
            finally:
                with self._thread_lock:
                    self._threads.discard(threading.current_thread())

    def _packet(self, run_id, packet):
        if not isinstance(packet, dict) or not isinstance(packet.get('data'), dict):
            raise ValueError('Worker event is invalid.')
        kind, data = packet.get('type'), packet['data']
        if len(json.dumps(packet)) > 30000:
            raise ValueError('Worker event is too large.')
        if kind == 'error':
            self._fail(run_id, data.get('message') or 'Research worker failed.')
            return
        if kind == 'usage':
            required = ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'web_search_requests', 'model_calls')
            if any(isinstance(data.get(key), bool) or not isinstance(data.get(key), int) or data[key] < 0 for key in required) or data['model_calls'] > 9:
                raise ValueError('Worker usage counters are invalid.')
            with transaction(self.engine) as session:
                run = session.get(SwarmRun, run_id)
                if any(data[key] < run.usage.get(key, 0) for key in required):
                    raise ValueError('Worker usage counters regressed.')
                run.usage = {key: data[key] for key in required}
            return
        if kind not in ('agent_started', 'search_query', 'source_found', 'evidence_note', 'estimate_submitted', 'estimate_revised', 'round_changed', 'final_result'):
            raise ValueError('Worker emitted an unsupported public event.')
        if kind == 'source_found':
            source = _source(data)
            if not source:
                raise ValueError('Worker source is not a safe public URL.')
            with Session(self.engine) as session:
                market_id = session.get(SwarmRun, run_id).market_id
            cache_sources(self.engine, market_id, [source], 'Anthropic web search')
            data = {'agent': data.get('agent'), **source}
        if kind in ('evidence_note', 'search_query'):
            if data.get('agent') not in (*AGENTS, 'Synthesizer'):
                raise ValueError('Unknown public evidence agent.')
            key = 'text' if kind == 'evidence_note' else 'query'
            if not isinstance(data.get(key), str) or not data[key] or len(data[key]) > 700:
                raise ValueError('Public evidence text is invalid.')
            if kind == 'search_query' and data['agent'] in ('Market Reader', 'Synthesizer'):
                raise ValueError('This agent is not permitted to search.')
        with transaction(self.engine) as session:
            run = session.get(SwarmRun, run_id)
            if run.status in TERMINAL:
                raise ValueError('Worker emitted events after termination.')
            if session.scalar(select(func.count()).select_from(SwarmEvent).where(SwarmEvent.run_id == run_id)) >= 6000:
                raise ValueError('Research public-event limit reached.')
            if kind == 'agent_started' and (data.get('agent') not in (*AGENTS, 'Synthesizer') or data.get('round') not in (1, 2, 3)):
                raise ValueError('Invalid agent start event.')
            if kind == 'round_changed' and data.get('round') not in (2, 3):
                raise ValueError('Invalid debate round.')
            if kind == 'search_query':
                started = session.scalars(select(SwarmEvent).where(SwarmEvent.run_id == run_id, SwarmEvent.type == 'agent_started').order_by(SwarmEvent.id.desc())).all()
                own_start = next((event for event in started if event.data.get('agent') == data['agent']), None)
                previous_queries = session.scalars(select(SwarmEvent).where(SwarmEvent.run_id == run_id, SwarmEvent.type == 'search_query')).all()
                if own_start is None or own_start.data.get('round') != 1 or sum(event.data.get('agent') == data['agent'] for event in previous_queries) >= 2:
                    raise ValueError('Searches are limited to two per eligible agent in the independent round.')
            if kind in ('estimate_submitted', 'estimate_revised'):
                validate_estimate(data, revised=kind == 'estimate_revised')
                observed_urls = {row.url for row in session.scalars(select(ResearchSource).where(ResearchSource.market_id == run.market_id)).all()}
                if _safe_url(run.market.get('terms_url')):
                    observed_urls.add(run.market['terms_url'])
                if any(url not in observed_urls for url in data['sources']):
                    raise ValueError('An estimate cited a source that was never observed.')
                if kind == 'estimate_revised' and session.scalar(select(func.count()).select_from(SwarmEstimate).where(SwarmEstimate.run_id == run_id, SwarmEstimate.round == 1)) != 4:
                    raise ValueError('Debate started before all independent forecasts were available.')
                session.add(SwarmEstimate(run_id=run_id, agent=data['agent'], round=data['round'], probability=data['probability'], confidence=data['confidence'], reasons=data['reasons'], sources=data['sources'], revision_reason=data.get('revision_reason')))
            if kind == 'final_result':
                if datetime.fromisoformat(run.market['closes_at'].replace('Z', '+00:00')) <= datetime.now(timezone.utc):
                    raise ValueError('The market closed before research completed. No prospective forecast was recorded.')
                estimates = session.scalars(select(SwarmEstimate).where(SwarmEstimate.run_id == run_id, SwarmEstimate.round == 2)).all()
                probability = median_probability([row.probability for row in estimates])
                if len({row.agent for row in estimates}) != 4 or isinstance(data.get('probability'), bool) or not isinstance(data.get('probability'), (int, float)) or not math.isfinite(data['probability']) or not math.isclose(probability, data['probability'], abs_tol=1e-9):
                    raise ValueError('Final probability does not match the four revised estimates.')
                if not isinstance(data.get('summary'), str) or not data['summary'].strip() or len(data['summary']) > 1500 or not isinstance(data.get('disagreements'), str) or len(data['disagreements']) > 1000:
                    raise ValueError('Final public summary is invalid.')
                if not isinstance(data.get('reasons'), list) or len(data['reasons']) != 3 or any(not isinstance(r, str) or not r.strip() or len(r) > 500 for r in data['reasons']):
                    raise ValueError('Final summary requires three short reasons.')
                selected = probability if run.outcome == 'yes' else 1 - probability
                price = float(run.market['price'])
                data = {**data, 'probability': probability, 'outcome': run.outcome, 'selected_probability': selected, 'market_price': price, 'gap': selected - price,
                        'range': [min(row.probability for row in estimates), max(row.probability for row in estimates)], 'sources': cached_sources(self.engine, run.market_id)}
                run.result, run.status, run.completed_at = data, 'completed', timestamp()
            session.add(SwarmEvent(run_id=run_id, type=kind, data=data))

    def read(self, run_id, user_id):
        with Session(self.engine) as session:
            run = _owned_run(session, run_id, user_id)
            return {**_run_json(run), 'events': [_event_json(e) for e in session.scalars(select(SwarmEvent).where(SwarmEvent.run_id == run_id).order_by(SwarmEvent.id)).all()],
                    'estimates': [_estimate_json(e) for e in session.scalars(select(SwarmEstimate).where(SwarmEstimate.run_id == run_id).order_by(SwarmEstimate.round, SwarmEstimate.created_at)).all()]}

    def latest(self, market_id, user_id, outcome=None):
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=CACHE_MINUTES)).isoformat()
        with Session(self.engine) as session:
            _user(session, user_id)
            query = select(SwarmRun).where(SwarmRun.user_id == user_id, SwarmRun.market_id == market_id, SwarmRun.status == 'completed', SwarmRun.completed_at >= cutoff)
            if outcome:
                query = query.where(SwarmRun.outcome == outcome)
            row = session.scalar(query.order_by(SwarmRun.completed_at.desc()))
            return {'run': _run_json(row) if row else None}

    def events(self, run_id, user_id, after=0):
        with Session(self.engine) as session:
            run = _owned_run(session, run_id, user_id)
            rows = session.scalars(select(SwarmEvent).where(SwarmEvent.run_id == run_id, SwarmEvent.id > after).order_by(SwarmEvent.id).limit(6000)).all()
            return [_event_json(row) for row in rows], run.status

    def shutdown(self):
        self._stop.set()
        with Session(self.engine) as session:
            ids = session.scalars(select(SwarmRun.id).where(SwarmRun.status.in_(ACTIVE))).all()
        for run_id in ids:
            self._fail(run_id, 'Research was interrupted by server shutdown. No completed forecast is available.')


def refresh_swarm_forecasts(engine, feed):
    """Score prospective completed forecasts once from actual venue resolution."""
    with Session(engine) as session:
        candidates = [(r.id, dict(r.market)) for r in session.scalars(select(SwarmRun).where(SwarmRun.status == 'completed', SwarmRun.scored_at.is_(None))).all()]
    scored = 0
    for run_id, market in candidates:
        try:
            fresh = next((m for m in feed.event(market['event_ticker']) if m['id'] == market['id'] and m['outcome'] == 'yes'), None)
        except (ProviderError, KeyError):
            continue
        if fresh is None or fresh.get('status') not in ('settled', 'invalid'):
            continue
        resolution = fresh.get('resolution')
        if fresh['status'] != 'invalid' and resolution not in ('yes', 'no'):
            continue
        with transaction(engine) as session:
            run = session.get(SwarmRun, run_id)
            if run.scored_at:
                continue
            run.resolution = 'void' if fresh['status'] == 'invalid' else resolution
            if run.resolution != 'void':
                probability = run.result['probability']
                run.brier_score = (probability - (1 if resolution == 'yes' else 0)) ** 2
                forecast_side = 'yes' if probability >= .5 else 'no'
                price = run.market.get(forecast_side + '_price')
                try:
                    price = float(price)
                    if math.isfinite(price) and 0 < price < 1:
                        run.side_edge = (1 if resolution == forecast_side else 0) - price
                except (TypeError, ValueError):
                    pass
            run.scored_at = timestamp()
            scored += 1
    return scored


def swarm_metrics(engine, user_id):
    with Session(engine) as session:
        _user(session, user_id)
        runs = session.scalars(select(SwarmRun).where(SwarmRun.user_id == user_id, SwarmRun.status == 'completed')).all()
        resolved = [run for run in runs if run.resolution in ('yes', 'no')]
        edges = [run.side_edge for run in resolved if run.side_edge is not None]
        brier = [run.brier_score for run in resolved if run.brier_score is not None]
        return {'forecast_count': len(runs), 'resolved_count': len(resolved), 'void_count': sum(r.resolution == 'void' for r in runs),
                'brier_score': sum(brier) / len(brier) if brier else None, 'edge_score': sum(edges) / len(edges) if edges else None, 'edge_sample_count': len(edges)}


def register_swarm(app, engine, feed, reading, worker=node_worker):
    service = SwarmService(engine, feed, reading, worker)
    app.state.swarm = service
    service.recover_interrupted()
    previous_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def swarm_lifespan(application):
        async with previous_lifespan(application) as state:
            try:
                yield state
            finally:
                service.shutdown()
    app.router.lifespan_context = swarm_lifespan

    @app.post('/swarm/run')
    def start_run(payload: RunInput):
        return service.start(payload)

    @app.get('/swarm/runs/{run_id}')
    def read_run(run_id: str, user_id: str):
        return service.read(run_id, user_id)

    @app.get('/swarm/runs/{run_id}/stream')
    async def stream_run(run_id: str, request: Request, user_id: str, after: int = Query(default=0, ge=0)):
        service.events(run_id, user_id, after)
        header = request.headers.get('last-event-id')
        try:
            cursor = max(after, int(header)) if header else after
        except ValueError:
            raise HTTPException(400, 'Last-Event-ID must be an integer.') from None
        async def stream():
            nonlocal cursor
            heartbeat = 0
            while not await request.is_disconnected():
                events, status = service.events(run_id, user_id, cursor)
                for event in events:
                    cursor = event['id']
                    yield f"id: {cursor}\nevent: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
                if status in TERMINAL:
                    break
                heartbeat += 1
                if heartbeat % 20 == 0:
                    yield ': heartbeat\n\n'
                await asyncio.sleep(.5)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.get('/swarm/markets/{market_id}')
    def latest_market(market_id: str, user_id: str, outcome: Literal['yes', 'no'] | None = None):
        return service.latest(market_id, user_id, outcome)

    @app.get('/swarm/metrics')
    def metrics(user_id: str):
        with Session(engine) as session:
            _user(session, user_id)
        refresh_swarm_forecasts(engine, feed)
        return swarm_metrics(engine, user_id)

    return service
