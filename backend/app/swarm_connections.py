"""Saved forecast integration. Reading chips and records never invokes a model."""
import math
from datetime import datetime
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import User
from .squad_models import Squad, SquadMember, SquadLeg, SquadEvent
from .squad_metrics import track_record
from .swarm_models import SwarmRun, SwarmShare
from .swarm import RunInput, transaction


def _time(value):
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date if date.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def _members(session, squad_id):
    return set(session.scalars(select(SquadMember.user_id).where(SquadMember.squad_id == squad_id)).all())


def _scope(session, squad_id, user_id, leg_id=None):
    if not session.get(User, user_id) or user_id not in _members(session, squad_id):
        raise HTTPException(404, 'Squad not found.')
    squad = session.get(Squad, squad_id)
    leg = session.get(SquadLeg, leg_id) if leg_id else None
    if leg_id and (not leg or leg.squad_id != squad_id or not leg.active):
        raise HTTPException(404, 'Active squad leg not found.')
    return squad, leg


def _canonical(session, legs, owners):
    """One earliest completed forecast per instrument before the first pick lock.

    The prediction side is Yes at p>=.5. The buy price must be the observed quote
    for that exact side; a missing quote is never replaced with 1-minus-price.
    """
    cutoffs = {}
    for leg in legs:
        squad = session.get(Squad, leg.squad_id)
        dates = [_time(squad.locked_at), _time(squad.lock_at), _time(leg.closes_at)]
        if not dates[0] or not dates[2]:
            continue
        cutoff = min(d for d in dates if d)
        cutoffs[leg.market_id] = min(cutoffs.get(leg.market_id, cutoff), cutoff)
    runs = session.scalars(select(SwarmRun).where(SwarmRun.user_id.in_(owners), SwarmRun.market_id.in_(cutoffs), SwarmRun.status == 'completed').order_by(SwarmRun.completed_at, SwarmRun.id)).all()
    chosen = {}
    for run in runs:
        ended, closes = _time(run.completed_at), _time(run.market.get('closes_at'))
        p = (run.result or {}).get('probability')
        if (not ended or not closes or ended >= min(cutoffs[run.market_id], closes)
                or isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1):
            continue
        chosen.setdefault(run.market_id, run)
    return chosen


def _fact(run):
    p = run.result['probability']; side = 'yes' if p >= .5 else 'no'
    price = run.market.get(side + '_price')
    try:
        price = float(price)
        if not math.isfinite(price) or not 0 < price < 1: return None
    except (ValueError, TypeError): return None
    status = 'void' if run.resolution == 'void' else ('won' if run.resolution == side else 'lost') if run.resolution in ('yes', 'no') else 'open'
    return {'id': run.id, 'entry_price': price, 'status': status, 'category': run.market.get('category', 'other'),
            'active': True, 'locked': True, 'created_at': run.completed_at, 'resolved_at': run.scored_at}


def _squad_forecasts(session, squad):
    owners = _members(session, squad.id)
    legs = session.scalars(select(SquadLeg).where(SquadLeg.user_id.in_(owners), SquadLeg.active.is_(True), SquadLeg.locked.is_(True))).all()
    return _canonical(session, legs, owners)


def squad_swarm_record(session, squad):
    chosen = list(_squad_forecasts(session, squad).values())
    facts = [_fact(run) for run in chosen]
    record = track_record([f for f in facts if f])
    brier = [run.brier_score for run in chosen if run.brier_score is not None]
    record.update(forecast_count=len(chosen), unpriced_count=sum(f is None for f in facts),
                  brier_score=sum(brier)/len(brier) if brier else None)
    return record


def comparison(session, squad, user_id):
    # Detailed comparisons disclose only legs already visible in this squad.
    legs = session.scalars(select(SquadLeg).where(SquadLeg.squad_id == squad.id, SquadLeg.user_id == user_id, SquadLeg.active.is_(True), SquadLeg.locked.is_(True))).all()
    chosen = _squad_forecasts(session, squad)
    posted = set(session.scalars(select(SwarmShare.run_id).where(SwarmShare.squad_id == squad.id, SwarmShare.status == 'posted')).all())
    matched = []
    for leg in legs:
        run = chosen.get(leg.market_id)
        fact = _fact(run) if run and run.id in posted else None
        if leg.status not in ('won', 'lost') or not fact or fact['status'] not in ('won', 'lost'):
            continue
        actual = leg.outcome if leg.status == 'won' else ('no' if leg.outcome == 'yes' else 'yes')
        if run.resolution != actual: continue
        matched.append({'market_id': leg.market_id, 'title': leg.title, 'run_id': run.id, 'probability': run.result['probability'],
                        'friend_side': leg.outcome, 'swarm_side': 'yes' if run.result['probability'] >= .5 else 'no',
                        'friend_edge': (1 if leg.status == 'won' else 0)-float(leg.entry_price),
                        'swarm_edge': (1 if fact['status'] == 'won' else 0)-fact['entry_price']})
    n = len(matched)
    return {'matched_count': n, 'friend_edge': sum(m['friend_edge'] for m in matched)/n if n else None,
            'swarm_edge': sum(m['swarm_edge'] for m in matched)/n if n else None, 'markets': matched}


def post_ready_shares(engine, run_id):
    """Called after a real worker finishes and after registering an explicit ask.

    BEGIN IMMEDIATE plus a unique intent makes concurrent callbacks/retries post
    once. A failed run posts an error, never a fabricated probability.
    """
    with transaction(engine) as session:
        run = session.get(SwarmRun, run_id)
        if not run or run.status not in ('completed', 'failed'): return
        shares = session.scalars(select(SwarmShare).where(SwarmShare.run_id == run_id, SwarmShare.status == 'waiting')).all()
        for share in shares:
            leg = session.get(SquadLeg, share.leg_id)
            if run.status == 'failed' or not leg.active:
                share.status = 'failed'
                session.add(SquadEvent(squad_id=share.squad_id, user_id=share.user_id, leg_id=share.leg_id, type='swarm_error',
                                      body='Swarm research was not posted: ' + (run.error or 'the original pick was replaced.'), data={'run_id':run.id}))
                continue
            share.status = 'posted'
            session.add(SquadEvent(squad_id=share.squad_id, user_id=share.user_id, leg_id=share.leg_id, type='swarm_forecast', body=run.result['summary'],
                                  data={'run_id':run.id, 'market_id':run.market_id, 'title':leg.title, 'outcome':run.outcome,
                                        'probability':run.result['probability'], 'selected_probability':run.result['selected_probability'],
                                        'market_price':run.result['market_price'], 'gap':run.result['gap'], 'completed_at':run.completed_at,
                                        'sources':run.result.get('sources', []), 'research_only':True}))


class AskInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    leg_id: str = Field(min_length=1, max_length=100)


class ShareInput(AskInput):
    run_id: str = Field(min_length=1, max_length=100)


def register_swarm_connections(app, engine):
    def intent(squad_id, payload, run_id):
        with transaction(engine) as session:
            _, leg = _scope(session, squad_id, payload.user_id, payload.leg_id)
            run = session.get(SwarmRun, run_id)
            if not run or run.user_id != payload.user_id: raise HTTPException(404, 'Research run not found.')
            if run.market_id != leg.market_id or run.outcome != leg.outcome:
                raise HTTPException(409, 'The research contract and side must match this leg.')
            share = session.scalar(select(SwarmShare).where(SwarmShare.squad_id == squad_id, SwarmShare.leg_id == leg.id, SwarmShare.run_id == run_id))
            if not share: session.add(SwarmShare(squad_id=squad_id, leg_id=leg.id, run_id=run_id, user_id=payload.user_id))
        post_ready_shares(engine, run_id)
        with Session(engine) as session:
            share = session.scalar(select(SwarmShare).where(SwarmShare.squad_id == squad_id, SwarmShare.leg_id == payload.leg_id, SwarmShare.run_id == run_id))
            return {'run_id':run_id, 'status':share.status, 'squad_id':squad_id, 'leg_id':payload.leg_id}

    @app.post('/squads/{squad_id}/swarm/ask')
    def ask(squad_id: str, payload: AskInput):
        with Session(engine) as session:
            _, leg = _scope(session, squad_id, payload.user_id, payload.leg_id)
            request = RunInput(user_id=payload.user_id, market_id=leg.market_id, outcome=leg.outcome)
        cached = app.state.swarm.latest(request.market_id, request.user_id, request.outcome)['run']
        if cached:
            return intent(squad_id, payload, cached['id'])
        started = app.state.swarm.start(request)
        return intent(squad_id, payload, started['run_id'])

    @app.post('/squads/{squad_id}/swarm/share')
    def share(squad_id: str, payload: ShareInput):
        with Session(engine) as session:
            _scope(session, squad_id, payload.user_id, payload.leg_id)
            run = session.get(SwarmRun, payload.run_id)
            if not run or run.user_id != payload.user_id: raise HTTPException(404, 'Research run not found.')
            if run.status != 'completed': raise HTTPException(409, 'Only completed research can be shared.')
        return intent(squad_id, payload, payload.run_id)

    @app.get('/squads/{squad_id}/swarm/runs/{run_id}')
    def read_shared(squad_id: str, run_id: str, user_id: str):
        with Session(engine) as session:
            _scope(session, squad_id, user_id)
            shared = session.scalar(select(SwarmShare).where(SwarmShare.squad_id == squad_id, SwarmShare.run_id == run_id, SwarmShare.status == 'posted'))
            if not shared: raise HTTPException(404, 'Shared research run not found.')
            owner = session.get(SwarmRun, run_id).user_id
        return app.state.swarm.read(run_id, owner)

    # Reconcile a crash between completion and posting; never restart model calls.
    with Session(engine) as session:
        waiting = session.scalars(select(SwarmShare.run_id).where(SwarmShare.status == 'waiting')).all()
    for run_id in set(waiting): post_ready_shares(engine, run_id)
