"""Local squad collaboration over real Gemini market quotes.

Creating a slip records proposed picks. It never pretends a combined order,
escrow, payment, or agent forecast exists.
"""
import asyncio
import json
import secrets
import ipaddress
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .database import User, timestamp
from .providers import ProviderError
from .squad_models import Squad, SquadMember, SquadLeg, SquadVote, SquadEvent
from .squad_metrics import track_record, payout_plan
from .xrpl_models import XRPLSettlement


def _date(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if result.tzinfo is None: raise ValueError('Timezone required')
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError) as exc:
        raise ValueError('Use an ISO date with a UTC offset.') from exc


def _price(value):
    try:
        price = Decimal(str(value))
        if not price.is_finite() or not 0 < price < 1: raise ValueError()
        return price
    except (InvalidOperation, ValueError, TypeError): return None


class MemberInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)


class CreateSquad(MemberInput):
    name: str = Field(min_length=1, max_length=80)
    stake_cents: int = Field(ge=1, le=1000000)
    member_limit: int = Field(ge=2, le=6)
    lock_at: datetime

    @field_validator('name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Enter a squad name.')
        return value.strip()

    @field_validator('lock_at')
    @classmethod
    def future_utc(cls, value):
        if value.tzinfo is None: raise ValueError('Lock time must include a timezone.')
        value = value.astimezone(timezone.utc)
        if value <= datetime.now(timezone.utc): raise ValueError('Choose a future lock time.')
        return value


class JoinSquad(MemberInput):
    invite_code: str = Field(min_length=1, max_length=32)


class PickLeg(MemberInput):
    market_id: str = Field(min_length=1, max_length=200)
    outcome: Literal['yes', 'no']
    max_price: Decimal | None = Field(default=None, gt=0, lt=1)


class VoteLeg(MemberInput):
    leg_id: str = Field(min_length=1, max_length=100)
    reaction: Literal['agree', 'disagree']
    comment: str = Field(default='', max_length=300)


class SendMessage(MemberInput):
    body: str = Field(min_length=1, max_length=1000)

    @field_validator('body')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Enter a message.')
        return value.strip()


class ShareArticle(MemberInput):
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2000)
    summary: str = Field(default='', max_length=500)
    leg_id: str | None = Field(default=None, min_length=1, max_length=100)
    reaction: Literal['agree', 'disagree'] | None = None

    @field_validator('title')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Enter the article title.')
        return value.strip()

    @field_validator('url')
    @classmethod
    def public_url(cls, value):
        value = value.strip()
        parts = urlsplit(value)
        if parts.scheme not in ['https', 'http'] or not parts.hostname or parts.username or parts.password or any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError('Use a public HTTP or HTTPS source link.')
        hostname = parts.hostname.lower()
        if hostname in ['localhost', 'localhost.localdomain'] or hostname.endswith(('.local', '.localhost')):
            raise ValueError('Use a public source link.')
        try:
            if not ipaddress.ip_address(hostname).is_global: raise ValueError('Use a public source link.')
        except ValueError as exc:
            # Domain names are not IP literals; private IP literals are rejected.
            if ':' in hostname or all(part.isdigit() for part in hostname.split('.')): raise ValueError('Use a public source link.') from exc
        try: parts.port
        except ValueError as exc: raise ValueError('Use a valid source URL.') from exc
        return value

    @model_validator(mode='after')
    def reaction_needs_leg(self):
        if self.reaction and not self.leg_id: raise ValueError('Choose a leg when attaching a reaction.')
        return self


def register_squads(app, engine, feed):
    @contextmanager
    def db(write=False):
        with Session(engine) as session:
            try:
                if write: session.execute(text('BEGIN IMMEDIATE'))
                yield session
                if write: session.commit()
            except Exception:
                session.rollback()
                raise

    def get_user(session, user_id):
        user = session.get(User, user_id)
        if not user: raise HTTPException(404, 'User not found. Complete onboarding first.')
        return user

    def members(session, squad_id):
        return session.scalars(select(SquadMember).where(SquadMember.squad_id == squad_id).order_by(SquadMember.joined_at, SquadMember.id)).all()

    def active_legs(session, squad_id):
        return session.scalars(select(SquadLeg).where(SquadLeg.squad_id == squad_id, SquadLeg.active.is_(True)).order_by(SquadLeg.created_at, SquadLeg.id)).all()

    def member_squad(session, squad_id, user_id):
        get_user(session, user_id)
        squad = session.get(Squad, squad_id)
        membership = session.scalar(select(SquadMember).where(SquadMember.squad_id == squad_id, SquadMember.user_id == user_id))
        if not squad or not membership: raise HTTPException(404, 'Squad not found for this member.')
        return squad

    def event(session, squad, event_type, body, user_id=None, leg_id=None, data=None):
        row = SquadEvent(squad_id=squad.id, user_id=user_id, type=event_type, body=body, leg_id=leg_id, data=data)
        session.add(row)
        session.flush()
        return row

    def complete(session, squad):
        people = members(session, squad.id)
        picks = active_legs(session, squad.id)
        return len(people) == squad.member_limit and {person.user_id for person in people} == {leg.user_id for leg in picks}

    def lock(session, squad):
        if squad.status != 'open': return
        squad.locked_at = timestamp()
        if complete(session, squad):
            squad.status = 'locked'
            for leg in active_legs(session, squad.id): leg.locked = True
            event(session, squad, 'lock', 'Picks and reactions are locked. No combined order or escrow has been placed.')
        else:
            squad.status = 'incomplete'
            event(session, squad, 'incomplete', 'The deadline passed before every member joined and picked a leg. This slip cannot be settled.')

    def apply_deadline(session, squad):
        if squad.status == 'open' and _date(squad.lock_at) <= datetime.now(timezone.utc): lock(session, squad)

    def require_open(session, squad):
        apply_deadline(session, squad)
        if session.get(XRPLSettlement, squad.id):
            raise HTTPException(409, 'Escrow setup has frozen this squad. Picks, joins, and reactions cannot change.')
        if squad.status != 'open': raise HTTPException(409, 'This squad is locked. Picks, joins, and reactions are frozen.')

    def event_json(session, row):
        user = session.get(User, row.user_id) if row.user_id else None
        return {'id': row.id, 'type': row.type, 'user_id': row.user_id, 'user_name': user.name if user else 'Squad',
                'body': row.body, 'leg_id': row.leg_id, 'created_at': row.created_at, 'data': row.data}

    def leg_fact(leg):
        return {'id': leg.id, 'user_id': leg.user_id, 'entry_price': leg.entry_price, 'category': leg.category,
                'status': leg.status, 'active': leg.active, 'locked': leg.locked,
                'created_at': leg.created_at, 'resolved_at': leg.resolved_at}

    def leaderboard(session, squad):
        from .swarm_connections import squad_swarm_record, comparison
        rows = []
        for member in members(session, squad.id):
            user = get_user(session, member.user_id)
            # Friendship profiles include that user's final picks across squads.
            history = session.scalars(select(SquadLeg).where(SquadLeg.user_id == member.user_id, SquadLeg.active.is_(True), SquadLeg.locked.is_(True))).all()
            votes = session.scalars(select(SquadVote).where(SquadVote.user_id == member.user_id)).all()
            vote_facts = []
            for vote in votes:
                leg = session.get(SquadLeg, vote.leg_id)
                if leg: vote_facts.append({'reaction': vote.reaction, 'leg': leg_fact(leg)})
            record = track_record([leg_fact(leg) for leg in history], vote_facts)
            record['swarm_comparison'] = comparison(session, squad, user.id)
            rows.append({'user_id': user.id, 'name': user.name, 'record': record})
        rows.append({'user_id': 'the-swarm', 'name': 'The Swarm', 'kind': 'swarm', 'record': squad_swarm_record(session, squad)})
        return rows

    def detail(session, squad):
        from .xrpl_service import squad_xrpl_detail
        apply_deadline(session, squad)
        people = members(session, squad.id)
        picks = active_legs(session, squad.id)
        legs = []
        for leg in picks:
            votes = session.scalars(select(SquadVote).where(SquadVote.leg_id == leg.id).order_by(SquadVote.created_at, SquadVote.id)).all()
            reaction_rows = [{'user_id': vote.user_id, 'user_name': get_user(session, vote.user_id).name,
                              'reaction': vote.reaction, 'comment': vote.comment, 'created_at': vote.created_at, 'updated_at': vote.updated_at} for vote in votes]
            legs.append({'id': leg.id, 'user_id': leg.user_id, 'user_name': get_user(session, leg.user_id).name,
                         'market_id': leg.market_id, 'event_ticker': leg.event_ticker, 'title': leg.title, 'label': leg.label,
                         'category': leg.category, 'outcome': leg.outcome, 'entry_price': leg.entry_price, 'closes_at': leg.closes_at,
                         'status': leg.status, 'locked': leg.locked, 'created_at': leg.created_at, 'resolved_at': leg.resolved_at,
                         'agree_count': sum(v.reaction == 'agree' for v in votes), 'disagree_count': sum(v.reaction == 'disagree' for v in votes), 'votes': reaction_rows})
        events = session.scalars(select(SquadEvent).where(SquadEvent.squad_id == squad.id).order_by(SquadEvent.id.desc()).limit(200)).all()
        events = [event_json(session, row) for row in reversed(events)]
        plan = None
        if squad.status == 'resolved' and complete(session, squad):
            plan = payout_plan(squad.stake_cents, [member.user_id for member in people], [leg.user_id for leg in picks if leg.status == 'lost'])
        xrpl = squad_xrpl_detail(session, squad.id)
        return {'id': squad.id, 'name': squad.name, 'creator_id': squad.creator_id, 'invite_code': squad.invite_code,
                'stake_cents': squad.stake_cents, 'member_limit': squad.member_limit, 'lock_at': squad.lock_at,
                'locked_at': squad.locked_at, 'created_at': squad.created_at, 'status': squad.status,
                'members': [{'user_id': member.user_id, 'name': get_user(session, member.user_id).name} for member in people],
                'legs': legs, 'messages': events, 'events': events, 'leaderboard': leaderboard(session, squad),
                'escrow': xrpl, 'xrpl': xrpl,
                'combo': {'status': 'not_placed', 'message': 'This is a proposed squad slip. No combined Gemini order has been placed.'},
                'payout_plan': plan, 'swarm': {'status': 'connected', 'message': 'Research forecasts use the same edge formula as friends. Only forecasts completed before picks locked qualify.'}}

    def provider(method, *args):
        try: return method(*args)
        except ProviderError as exc: raise HTTPException(503, str(exc)) from exc

    def validate_market(market, market_id, outcome):
        if market.get('id') != market_id or market.get('outcome') != outcome:
            raise HTTPException(409, 'The requested market side is unavailable.')
        if market.get('status') != 'active' or market.get('market_state') not in [None, 'open'] or market.get('resolution'):
            raise HTTPException(409, 'This contract is no longer open.')
        price = _price(market.get('price'))
        if price is None: raise HTTPException(409, 'This side has no valid buy quote.')
        try: closes = _date(market.get('closes_at'))
        except ValueError as exc: raise HTTPException(409, 'Gemini did not provide a valid market close time.') from exc
        if closes <= datetime.now(timezone.utc): raise HTTPException(409, 'This contract has closed.')
        if not market.get('event_ticker'): raise HTTPException(409, 'Gemini did not provide an event identifier.')
        return price, closes

    @app.get('/squads')
    def list_squads(user_id: str):
        with db(write=True) as session:
            get_user(session, user_id)
            squad_ids = session.scalars(select(SquadMember.squad_id).where(SquadMember.user_id == user_id)).all()
            squads = session.scalars(select(Squad).where(Squad.id.in_(squad_ids)).order_by(Squad.created_at.desc())).all()
            return [detail(session, squad) for squad in squads]

    @app.post('/squads', status_code=201)
    def create_squad(payload: CreateSquad):
        with db(write=True) as session:
            user = get_user(session, payload.user_id)
            code = secrets.token_hex(4).upper()
            while session.scalar(select(Squad.id).where(Squad.invite_code == code)): code = secrets.token_hex(4).upper()
            squad = Squad(creator_id=user.id, name=payload.name, invite_code=code, stake_cents=payload.stake_cents,
                          member_limit=payload.member_limit, lock_at=payload.lock_at.isoformat())
            session.add(squad); session.flush()
            session.add(SquadMember(squad_id=squad.id, user_id=user.id)); session.flush()
            event(session, squad, 'create', f'{user.name} created the squad.', user.id)
            return detail(session, squad)

    @app.get('/squads/markets')
    def available_markets(user_id: str):
        with db() as session: get_user(session, user_id)
        grouped = {}
        for market in provider(feed.markets):
            try: price, closes = validate_market(market, market.get('id'), market.get('outcome'))
            except HTTPException: continue
            if market.get('outcome') not in ['yes', 'no']: continue
            row = grouped.setdefault(market['id'], {'id': market['id'], 'market_id': market['id'], 'event_ticker': market['event_ticker'],
                                                     'title': market.get('title', ''), 'label': market.get('label', ''), 'category': market.get('category', ''),
                                                     'closes_at': closes.isoformat(), 'prices': {}, 'outcomes': []})
            row['prices'][market['outcome']] = str(price)
            row['outcomes'].append({'outcome': market['outcome'], 'price': str(price)})
        return [row for row in grouped.values() if set(row['prices']) == {'yes', 'no'}][:40]

    def join(session, squad, user_id):
        user = get_user(session, user_id)
        require_open(session, squad)
        people = members(session, squad.id)
        if any(member.user_id == user_id for member in people): return detail(session, squad)
        if len(people) >= squad.member_limit: raise HTTPException(409, 'This squad is full.')
        session.add(SquadMember(squad_id=squad.id, user_id=user_id)); session.flush()
        event(session, squad, 'join', f'{user.name} joined the squad.', user_id)
        return detail(session, squad)

    @app.post('/squads/join')
    def join_by_code(payload: JoinSquad):
        with db(write=True) as session:
            squad = session.scalar(select(Squad).where(Squad.invite_code == payload.invite_code.strip().upper()))
            if not squad: raise HTTPException(404, 'Invite code not found.')
            return join(session, squad, payload.user_id)

    @app.get('/squads/{squad_id}')
    def get_squad(squad_id: str, user_id: str):
        with db(write=True) as session: return detail(session, member_squad(session, squad_id, user_id))

    @app.post('/squads/{squad_id}/join')
    def join_by_id(squad_id: str, payload: MemberInput):
        with db(write=True) as session:
            squad = session.get(Squad, squad_id)
            if not squad: raise HTTPException(404, 'Squad not found.')
            return join(session, squad, payload.user_id)

    @app.post('/squads/{squad_id}/legs')
    def choose_leg(squad_id: str, payload: PickLeg):
        # Validate membership before contacting providers; recheck under the write lock.
        with db() as session:
            squad = member_squad(session, squad_id, payload.user_id)
            if squad.status != 'open' or _date(squad.lock_at) <= datetime.now(timezone.utc):
                raise HTTPException(409, 'This squad is locked. Picks are frozen.')
        market = provider(feed.market, payload.market_id, payload.outcome)
        price, closes = validate_market(market, payload.market_id, payload.outcome)
        if payload.max_price is not None and price > payload.max_price:
            raise HTTPException(409, 'The Gemini buy price increased. Review the latest quote before choosing.')
        with db(write=True) as session:
            squad = member_squad(session, squad_id, payload.user_id); require_open(session, squad)
            old = session.scalar(select(SquadLeg).where(SquadLeg.squad_id == squad.id, SquadLeg.user_id == payload.user_id, SquadLeg.active.is_(True)))
            if old and old.market_id == payload.market_id and old.outcome == payload.outcome: return detail(session, squad)
            if old: old.active = False
            leg = SquadLeg(squad_id=squad.id, user_id=payload.user_id, market_id=payload.market_id, outcome=payload.outcome,
                           event_ticker=market['event_ticker'], title=market.get('title', ''), label=market.get('label', ''),
                           category=market.get('category', '') or 'other', entry_price=str(price), closes_at=closes.isoformat())
            session.add(leg); session.flush()
            name = get_user(session, payload.user_id).name
            event(session, squad, 'swap' if old else 'pick', f"{name} {'swapped to' if old else 'picked'} {payload.outcome.upper()}: {leg.label or leg.title} at {price}.", payload.user_id, leg.id)
            return detail(session, squad)

    @app.post('/squads/{squad_id}/votes')
    def react(squad_id: str, payload: VoteLeg):
        with db(write=True) as session:
            squad = member_squad(session, squad_id, payload.user_id); require_open(session, squad)
            leg = session.get(SquadLeg, payload.leg_id)
            if not leg or leg.squad_id != squad.id or not leg.active: raise HTTPException(404, 'Active squad leg not found.')
            vote = session.scalar(select(SquadVote).where(SquadVote.leg_id == leg.id, SquadVote.user_id == payload.user_id))
            comment = payload.comment.strip()
            if vote and vote.reaction == payload.reaction and vote.comment == comment: return detail(session, squad)
            if vote:
                vote.reaction = payload.reaction; vote.comment = comment; vote.updated_at = timestamp()
            else: session.add(SquadVote(leg_id=leg.id, user_id=payload.user_id, reaction=payload.reaction, comment=comment))
            name = get_user(session, payload.user_id).name
            body = f"{name} {'agreed' if payload.reaction == 'agree' else 'disagreed'} with {leg.label or leg.title}"
            if comment: body += f': {comment}'
            event(session, squad, 'vote', body, payload.user_id, leg.id)
            return detail(session, squad)

    @app.post('/squads/{squad_id}/messages')
    def send_message(squad_id: str, payload: SendMessage):
        with db(write=True) as session:
            squad = member_squad(session, squad_id, payload.user_id)
            event(session, squad, 'message', payload.body, payload.user_id)
            return detail(session, squad)

    @app.post('/squads/{squad_id}/articles')
    def share_article(squad_id: str, payload: ShareArticle):
        with db(write=True) as session:
            squad = member_squad(session, squad_id, payload.user_id)
            leg = session.get(SquadLeg, payload.leg_id) if payload.leg_id else None
            if payload.leg_id and (not leg or leg.squad_id != squad.id or not leg.active):
                raise HTTPException(404, 'Active squad leg not found.')
            name = get_user(session, payload.user_id).name
            if payload.reaction:
                require_open(session, squad)
                vote = session.scalar(select(SquadVote).where(SquadVote.leg_id == leg.id, SquadVote.user_id == payload.user_id))
                if vote:
                    vote.reaction = payload.reaction; vote.comment = payload.summary.strip()[:300]; vote.updated_at = timestamp()
                else:
                    session.add(SquadVote(leg_id=leg.id, user_id=payload.user_id, reaction=payload.reaction, comment=payload.summary.strip()[:300]))
                event(session, squad, 'vote', f"{name} {'agreed' if payload.reaction == 'agree' else 'disagreed'} with {leg.label or leg.title} and shared a source.", payload.user_id, leg.id)
            event(session, squad, 'article', f'{name} shared: {payload.title}', payload.user_id, payload.leg_id,
                  {'title': payload.title, 'url': payload.url, 'summary': payload.summary.strip(), 'reaction': payload.reaction})
            return detail(session, squad)

    @app.post('/squads/{squad_id}/lock')
    def lock_early(squad_id: str, payload: MemberInput):
        with db(write=True) as session:
            squad = member_squad(session, squad_id, payload.user_id)
            if squad.creator_id != payload.user_id: raise HTTPException(403, 'Only the squad creator can lock early.')
            require_open(session, squad)
            if not complete(session, squad): raise HTTPException(409, 'Every squad member must join and choose one leg before locking.')
            lock(session, squad)
            return detail(session, squad)

    @app.post('/squads/{squad_id}/refresh')
    def refresh_results(squad_id: str, payload: MemberInput):
        with db(write=True) as session:
            squad = member_squad(session, squad_id, payload.user_id); apply_deadline(session, squad)
            if squad.status == 'open': raise HTTPException(409, 'Lock the full squad before refreshing results.')
            if squad.status == 'incomplete': raise HTTPException(409, 'This slip is incomplete and cannot be settled.')
            unresolved = [leg for leg in active_legs(session, squad.id) if leg.status == 'open']
            identifiers = [(leg.id, leg.event_ticker, leg.market_id) for leg in unresolved]
        results = {}
        for ticker in dict.fromkeys(ticker for _, ticker, _ in identifiers):
            results[ticker] = provider(feed.event, ticker)
        from .swarm import refresh_swarm_forecasts
        refresh_swarm_forecasts(engine, feed)
        with db(write=True) as session:
            squad = member_squad(session, squad_id, payload.user_id)
            for leg in active_legs(session, squad.id):
                if leg.status != 'open': continue
                market = next((row for row in results.get(leg.event_ticker, []) if row.get('id') == leg.market_id), None)
                resolution = str(market.get('resolution') or '').lower() if market else ''
                if market and market.get('status') == 'invalid':
                    leg.status = 'void'
                elif resolution in ['yes', 'no']:
                    leg.status = 'won' if resolution == leg.outcome else 'lost'
                elif resolution in ['invalid', 'void', 'voided']:
                    leg.status = 'void'
                else: continue
                leg.resolved_at = timestamp()
                event(session, squad, 'result', f'{get_user(session, leg.user_id).name}\'s {leg.outcome.upper()} pick resolved {leg.status}: {leg.label or leg.title}.', leg.user_id, leg.id)
            if complete(session, squad) and all(leg.status in ['won', 'lost', 'void'] for leg in active_legs(session, squad.id)):
                squad.status = 'resolved'
            return detail(session, squad)

    @app.get('/squads/{squad_id}/events')
    async def stream_events(squad_id: str, request: Request, user_id: str, after: int = Query(default=0, ge=0)):
        with db() as session: member_squad(session, squad_id, user_id)
        try:
            after = max(after, int(request.headers.get('last-event-id', '0')))
        except (ValueError, TypeError): pass

        async def stream():
            cursor = after
            idle = 0
            while not await request.is_disconnected():
                with db() as session:
                    member_squad(session, squad_id, user_id)
                    rows = session.scalars(select(SquadEvent).where(SquadEvent.squad_id == squad_id, SquadEvent.id > cursor).order_by(SquadEvent.id).limit(100)).all()
                    batch = [event_json(session, row) for row in rows]
                for row in batch:
                    cursor = row['id']
                    yield f"id: {cursor}\nevent: squad\ndata: {json.dumps(row, separators=(',', ':'))}\n\n"
                if not batch:
                    idle += 1
                    if idle % 15 == 0: yield ': heartbeat\n\n'
                else: idle = 0
                await asyncio.sleep(1)

        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
