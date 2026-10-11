"""Real XRPL test-token escrow, with durable intents before external effects.

The Node executor handles signing and AES-GCM secrets. This service holds the
database journal and never exposes encrypted or plaintext private values.
"""
import base64
import json
import os
import re
import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .database import User, timestamp
from .providers import ProviderError
from .squad_models import Squad, SquadMember, SquadLeg, SquadEvent
from .squad_metrics import payout_plan
from .xrpl_models import XRPLWallet, XRPLSettlement, XRPLEscrow, XRPLOperation

RIPPLE_EPOCH = 946684800
ROOT = Path(__file__).resolve().parents[2]
EXPLORERS = {'testnet': 'https://testnet.xrpl.org/transactions/', 'devnet': 'https://devnet.xrpl.org/transactions/'}


def execute_cli(payload):
    runner = ROOT / 'xrpl/node_modules/.bin/tsx'
    if not runner.exists(): raise RuntimeError('Install the XRPL executor with cd xrpl && npm ci.')
    completed = subprocess.run([str(runner), str(ROOT / 'xrpl/cli.ts')], input=json.dumps(payload),
                               text=True, capture_output=True, timeout=180, cwd=ROOT)
    # Do not echo stderr or request data: private values pass only through stdin.
    try: result = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError('XRPL executor stopped without a valid result. The operation must be reconciled before retrying.') from exc
    if not isinstance(result, dict): raise RuntimeError('XRPL executor returned an invalid result.')
    return result


def _network():
    network = os.getenv('XRPL_NETWORK', 'testnet')
    if network not in EXPLORERS: raise HTTPException(503, 'XRPL_NETWORK must be testnet or devnet. Mainnet is disabled.')
    return network


def _configured():
    value = os.getenv('XRPL_WALLET_KEY', '')
    try:
        decoded = base64.b64decode(value, validate=True)
        return len(decoded) == 32 and base64.b64encode(decoded).decode() == value
    except (ValueError, TypeError): return False


def xrpl_configured():
    """An optional onboarding hook must never enable an unsupported network."""
    return os.getenv('XRPL_NETWORK', 'testnet') in EXPLORERS and _configured()


def _public_transactions(records, network):
    rows = []
    for record in records or []:
        if not isinstance(record, dict): continue
        hash = str(record.get('hash', ''))
        if not re.fullmatch(r'[0-9A-Fa-f]{64}', hash): continue
        rows.append({'hash': hash.upper(), 'explorer_url': EXPLORERS[network] + hash.upper(),
                     'type': str(record.get('type', 'Transaction'))[:80], 'label': str(record.get('label', 'XRPL transaction'))[:120],
                     'result': str(record.get('result', 'unknown'))[:80], 'ledger_index': record.get('ledger_index')})
    return rows


def squad_xrpl_detail(session, squad_id):
    settlement = session.get(XRPLSettlement, squad_id)
    if not settlement:
        network = os.getenv('XRPL_NETWORK','testnet')
        if network not in EXPLORERS:
            return {'status':'unavailable','network':None,'currency':'SPC','message':'XRPL_NETWORK is unsupported. Collaboration remains available; XRPL transfers are disabled.','escrows':[],'transactions':[]}
        return {'status': 'not_configured', 'network': network, 'currency': 'SPC',
                'message': 'No SPC test-token collateral is locked for this squad.', 'escrows': [], 'transactions': []}
    wallet = session.get(XRPLWallet, settlement.wallet_id) if settlement.wallet_id else None
    escrows = session.scalars(select(XRPLEscrow).where(XRPLEscrow.squad_id == squad_id).order_by(XRPLEscrow.user_id)).all()
    operations = session.scalars(select(XRPLOperation).where(XRPLOperation.squad_id == squad_id).order_by(XRPLOperation.created_at)).all()
    return {'status': settlement.status, 'network': settlement.network, 'currency': 'SPC',
            'token_label': 'Custom SPC test tokens, not RLUSD or real dollars', 'custodial': True,
            'settlement_address': wallet.address if wallet and wallet.status == 'ready' else None,
            'cancel_after': settlement.cancel_after, 'message': settlement.message,
            'plan': settlement.plan, 'batch_hash': settlement.batch_hash,
            'batch_explorer_url': EXPLORERS[settlement.network] + settlement.batch_hash if settlement.batch_hash else None,
            'escrows': [{'user_id': escrow.user_id, 'status': escrow.status, 'amount_cents': escrow.amount_cents,
                        'owner': escrow.owner, 'offer_sequence': escrow.offer_sequence, 'cancel_after': escrow.cancel_after,
                        'create_hash': escrow.create_hash, 'finish_hash': escrow.finish_hash, 'cancel_hash': escrow.cancel_hash} for escrow in escrows],
            'transactions': [record for operation in operations for record in _public_transactions(operation.transactions, settlement.network)],
            'settled_at': settlement.settled_at}


class MemberInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)


class XRPLService:
    def __init__(self, engine, feed, executor=execute_cli):
        self.engine, self.feed, self.executor = engine, feed, executor

    @contextmanager
    def db(self, write=False):
        with Session(self.engine) as session:
            try:
                if write: session.execute(text('BEGIN IMMEDIATE'))
                yield session
                if write: session.commit()
            except Exception:
                session.rollback()
                raise

    def user(self, session, user_id):
        user = session.get(User, user_id)
        if not user: raise HTTPException(404, 'User not found. Complete onboarding first.')
        return user

    def squad(self, session, squad_id, user_id, creator=False):
        self.user(session, user_id)
        squad = session.get(Squad, squad_id)
        membership = session.scalar(select(SquadMember).where(SquadMember.squad_id == squad_id, SquadMember.user_id == user_id))
        if not squad or not membership: raise HTTPException(404, 'Squad not found for this member.')
        if creator and squad.creator_id != user_id: raise HTTPException(403, 'Only the squad creator can settle collateral.')
        return squad

    def ready(self):
        network = _network()
        if not _configured(): raise HTTPException(503, 'Configure a stable XRPL_WALLET_KEY (base64 32 bytes) before creating custodial test wallets.')
        return network

    def read(self, operation, **fields):
        network = _network()
        try: result = self.executor({'operation': operation, 'network': network, **fields})
        except Exception as exc: raise HTTPException(503, 'XRPL test network is unavailable. No transfer was requested by this read.') from exc
        if not result.get('ok'): raise HTTPException(503, str(result.get('error') or 'XRPL test-network read failed.')[:300])
        status = result.get('status') or {}
        if status.get('network') != network or status.get('network_id') != (1 if network == 'testnet' else 2):
            raise HTTPException(503, 'XRPL executor did not confirm the required test network.')
        return result

    def status(self):
        network = _network()
        if not _configured():
            return {'configured': False, 'network': network, 'currency': 'SPC', 'custodial': True,
                    'message': 'Configure XRPL_WALLET_KEY to enable encrypted custodial test wallets. No funds are locked.'}
        status = self.read('probe')['status']
        with self.db() as session: issuer = session.get(XRPLWallet, f'issuer:{network}')
        return {'configured': True, 'network': network, 'currency': 'SPC', 'custodial': True,
                'token_label': 'Custom SPC test token, not RLUSD or redeemable USD', 'status': status,
                'issuer_ready': bool(issuer and issuer.status == 'ready'), 'issuer_address': issuer.address if issuer and issuer.status == 'ready' else None}

    def _run(self, key, request, resources, done, *, squad_id=None, user_id=None, failed=None, prepare=None):
        network = self.ready()
        with self.db(write=True) as session:
            row = session.scalar(select(XRPLOperation).where(XRPLOperation.key == key))
            if row and row.status in ['pending', 'unknown']:
                raise HTTPException(409, 'This XRPL operation is pending or uncertain. Inspect its transaction hashes before any retry.')
            if row and row.status == 'succeeded': return
            active = session.scalars(select(XRPLOperation).where(XRPLOperation.status.in_(['pending', 'unknown']))).all()
            if any(set(item.resource_keys).intersection(resources) for item in active):
                raise HTTPException(409, 'A wallet has a pending or uncertain XRPL operation. Reconcile it before another transfer.')
            if prepare: prepare(session)
            if not row:
                row = XRPLOperation(key=key, squad_id=squad_id, user_id=user_id, operation=request['operation'],
                                    network=network, resource_keys=resources, status='pending', transactions=[])
                session.add(row)
            else: row.status = 'pending'; row.message = None; row.updated_at = timestamp()
            session.flush(); operation_id = row.id
        uncertain = False
        records = []
        try:
            result = self.executor({'network': network, **request})
            if not isinstance(result, dict): raise ValueError('Invalid result')
            records = _public_transactions(result.get('transactions'), network)
            if not result.get('ok'):
                uncertain = any(record['result'] == 'submitted_unconfirmed' for record in records)
                if request['operation'] in ['setup', 'wallet-create'] and records: uncertain = True
                if request['operation'] == 'batch-payout' and any(record['result'] == 'tesSUCCESS' for record in records): uncertain = True
                message = str(result.get('error') or 'XRPL operation failed.')[:300]
            else:
                message = None
                status = result.get('status') or {}
                if status.get('network') != network or status.get('network_id') != (1 if network == 'testnet' else 2):
                    raise ValueError('Wrong network confirmation')
                # Missing confirmation after mutation is uncertain, never success.
                if request['operation'] not in ['wallet-create'] and not records: raise ValueError('No validated transaction record')
                if any(record['result'] != 'tesSUCCESS' or not record.get('ledger_index') for record in records): raise ValueError('Unconfirmed transaction')
                if request['operation'] in ['escrow-create','escrow-finish','escrow-cancel','batch-payout'] and not any(record['hash'] == str(result.get('hash','')).upper() for record in records):
                    raise ValueError('Returned transaction hash was not confirmed')
        except Exception:
            result, message, uncertain = {}, 'XRPL submission may have happened. Inspect account history and saved hashes before any retry.', True
        with self.db(write=True) as session:
            row = session.get(XRPLOperation, operation_id)
            row.transactions = [*(row.transactions or []), *records]
            row.updated_at = timestamp()
            if message:
                row.status = 'unknown' if uncertain else 'failed'; row.message = message
                if failed: failed(session, uncertain, message)
            else:
                try: done(session, result)
                except Exception:
                    # A valid on-chain action with an unusable response must not
                    # be retried. Preserve its hashes for manual reconciliation.
                    row.status = 'unknown'; row.message = 'XRPL validated a transaction but its local result could not be applied. Reconcile before retrying.'
                    if failed: failed(session, True, row.message)
                    message = row.message
                else: row.status = 'succeeded'
        if message: raise HTTPException(503, message)

    def setup(self, user_id):
        network = self.ready()
        with self.db(write=True) as session:
            self.user(session, user_id)
            issuer = session.get(XRPLWallet, f'issuer:{network}')
            if issuer and issuer.status == 'ready': return self.status()
            if not issuer:
                session.add(XRPLWallet(id=f'issuer:{network}', role='issuer', network=network, status='creating'))
                session.add(XRPLWallet(id=f'treasury:{network}', role='treasury', network=network, status='creating'))
        def done(session, result):
            for role, field in [('issuer', 'issuer'), ('treasury', 'settlement')]:
                wallet = session.get(XRPLWallet, f'{role}:{network}')
                wallet.address = result[field]['address']; wallet.encrypted_seed = result[field]['encrypted_seed']; wallet.status = 'ready'
        def failed(session, unknown, message):
            for role in ['issuer', 'treasury']: session.get(XRPLWallet, f'{role}:{network}').status = 'unknown' if unknown else 'failed'
        self._run(f'setup:{network}', {'operation': 'setup'}, [f'issuer:{network}'], done, user_id=user_id, failed=failed)
        return self.status()

    def wallet(self, user_id, create=False):
        network = _network()
        with self.db() as session:
            self.user(session, user_id)
            row = session.get(XRPLWallet, f'member:{network}:{user_id}')
            operation = session.scalar(select(XRPLOperation).where(XRPLOperation.key == f'wallet:{network}:{user_id}'))
            if row and (row.status == 'unknown' or row.status == 'creating' and operation and operation.status in ['pending','unknown','succeeded']):
                raise HTTPException(409, 'This test-wallet creation is pending or uncertain. Reconcile before retrying.')
        if (not row or row.status != 'ready') and create:
            self.setup(user_id)
            with self.db(write=True) as session:
                row = session.get(XRPLWallet, f'member:{network}:{user_id}')
                issuer = session.get(XRPLWallet, f'issuer:{network}')
                issuer_input = {'address': issuer.address, 'encrypted_seed': issuer.encrypted_seed}
                if not row:
                    row = XRPLWallet(id=f'member:{network}:{user_id}', user_id=user_id, role='member', network=network, status='creating')
                    session.add(row)
            def done(session, result):
                wallet = session.get(XRPLWallet, f'member:{network}:{user_id}')
                wallet.address = result['wallet']['address']; wallet.encrypted_seed = result['wallet']['encrypted_seed']; wallet.status = 'ready'
            def failed(session, unknown, message): session.get(XRPLWallet, f'member:{network}:{user_id}').status = 'unknown' if unknown else 'failed'
            self._run(f'wallet:{network}:{user_id}', {'operation': 'wallet-create', 'issuer': issuer_input},
                      [f'issuer:{network}', f'member:{network}:{user_id}'], done, user_id=user_id, failed=failed)
        with self.db() as session:
            row = session.get(XRPLWallet, f'member:{network}:{user_id}'); issuer = session.get(XRPLWallet, f'issuer:{network}')
            if not row or row.status != 'ready': return {'status': 'not_created', 'network': network, 'currency': 'SPC', 'custodial': True}
            address, issuer_address = row.address, issuer.address if issuer and issuer.status == 'ready' else None
        balances = self.read('account', address=address, issuer_address=issuer_address)
        return {'status': 'ready', 'network': network, 'address': address, 'currency': 'SPC', 'custodial': True,
                'token_label': 'Custom SPC test token; not RLUSD or real dollars', 'balance': balances.get('token_balance'), 'xrp_balance': balances.get('xrp_balance')}

    def create_wallet_in_background(self, user_id):
        if not xrpl_configured(): return
        try: self.wallet(user_id, create=True)
        except Exception:
            # Financial intent/errors are persisted by _run. Onboarding itself
            # must remain usable during faucet or network outages.
            return

    def detail(self, squad_id, user_id):
        with self.db() as session:
            self.squad(session, squad_id, user_id)
            return squad_xrpl_detail(session, squad_id)

    def lock(self, squad_id, user_id):
        network = self.ready()
        with self.db(write=True) as session:
            squad = self.squad(session, squad_id, user_id)
            if not 3 <= squad.member_limit <= 6: raise HTTPException(409, 'XRPL atomic collateral settlement requires 3 to 6 squad members; two-member payouts cannot always form a Batch.')
            people = session.scalars(select(SquadMember).where(SquadMember.squad_id == squad_id)).all()
            legs = session.scalars(select(SquadLeg).where(SquadLeg.squad_id == squad_id, SquadLeg.active.is_(True))).all()
            if len(people) != squad.member_limit or {member.user_id for member in people} != {leg.user_id for leg in legs} or len(legs) != len(people):
                raise HTTPException(409, 'Every squad member must join and pick one leg before any collateral is locked.')
            current = session.get(XRPLSettlement, squad_id)
            existing = session.scalar(select(XRPLEscrow).where(XRPLEscrow.squad_id == squad_id, XRPLEscrow.user_id == user_id))
            if existing and existing.status == 'locked': return squad_xrpl_detail(session, squad_id)
            existing_operation = session.scalar(select(XRPLOperation).where(XRPLOperation.key == f'escrow:{squad_id}:{user_id}'))
            if existing and (existing.status in ['unknown', 'releasing', 'released', 'refunding', 'refunded'] or existing.status == 'creating' and existing_operation and existing_operation.status in ['pending','unknown','succeeded']):
                raise HTTPException(409, 'This member escrow is pending or terminal. It cannot be locked again.')
            if current and current.status in ['unknown', 'releasing', 'settled', 'refunding', 'refunded']:
                raise HTTPException(409, 'This squad collateral is already settling, refunded, or uncertain.')
            if squad.status not in ['open', 'locked']: raise HTTPException(409, 'Collateral can only be locked for an open or locked squad.')
            try:
                close_times = [datetime.fromisoformat(leg.closes_at.replace('Z','+00:00')) for leg in legs]
                if any(time.tzinfo is None for time in close_times): raise ValueError()
                latest = max(close_times)
            except (ValueError, TypeError): raise HTTPException(409, 'All legs need valid expected close times before collateral can be locked.')
            if any(time <= datetime.now(timezone.utc) for time in close_times): raise HTTPException(409, 'A squad leg has already closed. Every member must lock collateral before any leg closes.')
            facts = [(leg.event_ticker,leg.market_id,leg.outcome) for leg in legs]
            plan = payout_plan(squad.stake_cents, [member.user_id for member in people], [])
            amount = next(row['collateral_cents'] for row in plan['members'] if row['user_id'] == user_id)
            if amount <= 0: raise HTTPException(409, 'Stake is too small to lock positive collateral for every member.')
            if not current:
                cancel_after = int((latest + timedelta(days=2)).timestamp()) - RIPPLE_EPOCH
                current = XRPLSettlement(squad_id=squad_id, network=network, status='gathering', cancel_after=cancel_after)
                session.add(current)
            elif current.network != network: raise HTTPException(409, 'This squad was created on a different XRPL test network.')
            # Freezing here makes a mutation hook deterministic before any call.
            squad.status = 'locked'; squad.locked_at = squad.locked_at or timestamp()
            for leg in legs: leg.locked = True
        self.wallet(user_id, create=True)
        self._squad_wallet(squad_id, user_id)
        # Faucet provisioning can take a minute. Recheck every public market at
        # the last moment before a member can commit collateral.
        self._check_open_results(facts)
        with self.db(write=True) as session:
            wallet = session.get(XRPLWallet, f'member:{network}:{user_id}')
            issuer = session.get(XRPLWallet, f'issuer:{network}')
            settlement = session.get(XRPLSettlement, squad_id)
            destination = session.get(XRPLWallet, settlement.wallet_id)
            escrow = session.scalar(select(XRPLEscrow).where(XRPLEscrow.squad_id == squad_id, XRPLEscrow.user_id == user_id))
            if not escrow:
                escrow = XRPLEscrow(squad_id=squad_id, user_id=user_id, wallet_id=wallet.id, amount_cents=amount, cancel_after=settlement.cancel_after, status='creating')
                session.add(escrow); session.flush()
            escrow_id = escrow.id
            request = {'operation': 'escrow-create', 'encrypted_seed': wallet.encrypted_seed, 'destination': destination.address,
                       'issuer_address': issuer.address, 'amount_cents': amount, 'cancel_after': settlement.cancel_after}
        def done(session, result):
            escrow = session.get(XRPLEscrow, escrow_id)
            for field in ['owner','offer_sequence','condition','encrypted_fulfillment']: setattr(escrow, field, result[field])
            escrow.create_hash = result['hash']; escrow.status = 'locked'
            squad = session.get(Squad, squad_id)
            rows = session.scalars(select(XRPLEscrow).where(XRPLEscrow.squad_id == squad_id)).all()
            current = session.get(XRPLSettlement, squad_id)
            current.status = 'locked' if len(rows) == squad.member_limit and all(row.status == 'locked' for row in rows) else 'gathering'
            session.add(SquadEvent(squad_id=squad_id,user_id=user_id,type='escrow',body='SPC test-token collateral locked on XRPL.',data={'hash': result['hash'], 'amount_cents': amount, 'network': network}))
        def failed(session, unknown, message):
            session.get(XRPLEscrow, escrow_id).status = 'unknown' if unknown else 'failed'
            current = session.get(XRPLSettlement, squad_id); current.status = 'unknown' if unknown else 'gathering'; current.message = message
        def prepare(session):
            escrow = session.get(XRPLEscrow,escrow_id)
            if escrow.status not in ['creating','failed']: raise HTTPException(409,'This escrow already has an operation or a terminal result.')
            current = session.get(XRPLSettlement,squad_id)
            if current.status not in ['gathering','locked']: raise HTTPException(409,'Squad collateral state changed before this lock.')
            escrow.status = 'creating'
        self._run(f'escrow:{squad_id}:{user_id}', request, [f'member:{network}:{user_id}',f'escrow:{escrow_id}'], done, squad_id=squad_id, user_id=user_id, failed=failed, prepare=prepare)
        return self.detail(squad_id, user_id)

    def _check_open_results(self,facts):
        try:
            events={ticker:self.feed.event(ticker) for ticker in dict.fromkeys(fact[0] for fact in facts)}
        except ProviderError as exc: raise HTTPException(503,'Gemini cannot confirm every leg is still open. No collateral was submitted.') from exc
        for ticker,market_id,outcome in facts:
            market=next((row for row in events[ticker] if row.get('id')==market_id and row.get('outcome')==outcome),None)
            if not market or market.get('resolution') or market.get('status')!='active' or market.get('market_state') not in [None,'open']:
                raise HTTPException(409,'A squad leg is closed, resolved, or unavailable. Collateral cannot be added after outcomes are known.')
            closes=market.get('closes_at')
            if closes:
                try: time=datetime.fromisoformat(closes.replace('Z','+00:00'))
                except (ValueError,TypeError): raise HTTPException(409,'Gemini supplied an invalid market close time.')
                if time.tzinfo is None or time<=datetime.now(timezone.utc): raise HTTPException(409,'A squad leg closed during wallet setup. No collateral was submitted.')

    def _squad_wallet(self, squad_id, user_id):
        network = self.ready(); wallet_id = f'settlement:{network}:{squad_id}'
        with self.db(write=True) as session:
            wallet = session.get(XRPLWallet, wallet_id)
            if wallet and wallet.status == 'ready': return
            issuer = session.get(XRPLWallet, f'issuer:{network}')
            if not wallet: session.add(XRPLWallet(id=wallet_id, squad_id=squad_id, role='settlement', network=network, status='creating'))
            issuer_input = {'address': issuer.address, 'encrypted_seed': issuer.encrypted_seed}
        def done(session, result):
            wallet = session.get(XRPLWallet, wallet_id)
            wallet.address = result['wallet']['address']; wallet.encrypted_seed = result['wallet']['encrypted_seed']; wallet.status = 'ready'
            session.get(XRPLSettlement, squad_id).wallet_id = wallet_id
        def failed(session, unknown, message):
            session.get(XRPLWallet, wallet_id).status = 'unknown' if unknown else 'failed'
            current = session.get(XRPLSettlement, squad_id); current.status = 'unknown' if unknown else 'gathering'; current.message = message
        self._run(f'squad-wallet:{squad_id}', {'operation': 'wallet-create', 'issuer': issuer_input, 'fund_cents': 0},
                  [f'issuer:{network}',wallet_id],done,squad_id=squad_id,user_id=user_id,failed=failed)

    def settle(self, squad_id, user_id):
        network = self.ready()
        with self.db() as session:
            squad = self.squad(session,squad_id,user_id,creator=True)
            settlement = session.get(XRPLSettlement,squad_id)
            if settlement and settlement.status == 'settled': return squad_xrpl_detail(session,squad_id)
            if not settlement or settlement.status not in ['locked','releasing']: raise HTTPException(409,'Every member must have confirmed locked collateral before settlement. Pending or uncertain operations must be reconciled.')
            if settlement.network != network: raise HTTPException(409,'Wrong XRPL test network for this squad.')
            escrows = session.scalars(select(XRPLEscrow).where(XRPLEscrow.squad_id==squad_id)).all()
            if len(escrows) != squad.member_limit or any(row.status not in ['locked','released'] for row in escrows): raise HTTPException(409,'All member collateral must be confirmed locked or already released.')
            legs = session.scalars(select(SquadLeg).where(SquadLeg.squad_id==squad_id,SquadLeg.active.is_(True),SquadLeg.locked.is_(True))).all()
            facts = [(leg.id,leg.user_id,leg.event_ticker,leg.market_id,leg.outcome) for leg in legs]
            if len(legs) != squad.member_limit: raise HTTPException(409,'The locked squad picks are incomplete.')
            members = [row.user_id for row in escrows]; stake = squad.stake_cents
        # Fresh public event endpoints, never stale persisted leg statuses.
        ledger_time = self.read('probe')['status'].get('ledger_close_time', 0)
        if ledger_time >= settlement.cancel_after:
            raise HTTPException(409, 'The escrow cancellation deadline has passed. Refund each member escrow instead of releasing collateral.')
        results = {}
        try:
            for ticker in dict.fromkeys(item[2] for item in facts): results[ticker] = self.feed.event(ticker)
        except ProviderError as exc: raise HTTPException(503,'Gemini results are unavailable. Collateral remains locked.') from exc
        resolved = {}; losers = []
        for leg_id, member_id, ticker, market_id, outcome in facts:
            market = next((row for row in results[ticker] if row.get('id') == market_id and row.get('outcome') == outcome),None)
            resolution = str(market.get('resolution') or '').lower() if market else ''
            if market and (market.get('status')=='invalid' or resolution in ['invalid','void','voided']): result='void'
            elif resolution in ['yes','no']: result='won' if resolution==outcome else 'lost'
            else: raise HTTPException(409,'Not every Gemini leg has a final published result. Collateral remains locked.')
            resolved[leg_id] = {'status':result,'market_id':market_id,'resolution':resolution,'event_ticker':ticker}
            if result=='lost': losers.append(member_id)
        plan = payout_plan(stake,members,losers)
        plan.update(status='prepared',currency='SPC',message='Payout plan prepared from freshly published Gemini results. SPC test-token collateral is being released.')
        if len([row for row in plan['members'] if row['payout_cents']>0])<2: raise HTTPException(409,'This plan cannot form an atomic Batch with at least two positive payments.')
        with self.db(write=True) as session:
            settlement = session.get(XRPLSettlement,squad_id)
            if settlement.status not in ['locked','releasing']: raise HTTPException(409,'Settlement state changed. Inspect its transaction journal.')
            if settlement.plan and settlement.plan != plan: raise HTTPException(409,'Published results changed after release began. Manual reconciliation is required.')
            settlement.status='releasing'; settlement.plan=plan; settlement.results=resolved
            for leg_id,fact in resolved.items():
                leg=session.get(SquadLeg,leg_id); leg.status=fact['status']; leg.resolved_at=leg.resolved_at or timestamp()
            session.get(Squad,squad_id).status='resolved'
        for member_id in sorted(members): self._finish(squad_id,user_id,member_id)
        with self.db() as session:
            settlement=session.get(XRPLSettlement,squad_id); sender=session.get(XRPLWallet,settlement.wallet_id); issuer=session.get(XRPLWallet,f'issuer:{network}')
            addresses={member:session.get(XRPLWallet,f'member:{network}:{member}').address for member in members}
            request={'operation':'batch-payout','encrypted_seed':sender.encrypted_seed,'issuer_address':issuer.address,
                     'payouts':[{'address':addresses[row['user_id']],'cents':row['payout_cents']} for row in plan['members']]}
            sender_id=sender.id
        def done(session,result):
            expected = sum(row['payout_cents']>0 for row in plan['members'])
            inner=result.get('inner_transactions') or []
            if len(inner)!=expected or any(row.get('result')!='tesSUCCESS' or not row.get('ledger_index') for row in inner): raise ValueError('Inner payments not confirmed')
            if len({row.get('hash') for row in inner})!=expected: raise ValueError('Inner payments are not distinct')
            balances={row.get('address'):row for row in result.get('balances',[])}
            for payout in request['payouts']:
                balance=balances.get(payout['address'])
                if not balance or balance.get('payout_cents')!=payout['cents']: raise ValueError('Missing intended payout proof')
                if (Decimal(str(balance['after']))-Decimal(str(balance['before'])))*100 != payout['cents']: raise ValueError('Recipient token balance did not match payout')
            settlement=session.get(XRPLSettlement,squad_id); settlement.status='settled'; settlement.batch_hash=result['hash']; settlement.settled_at=timestamp(); settlement.message='Every payout was confirmed in one all-or-nothing XRPL Batch using SPC test tokens.'
            settlement.plan={**plan,'status':'settled','message':'Every intended SPC test-token payout was confirmed in one atomic Batch.'}
            session.add(SquadEvent(squad_id=squad_id,user_id=user_id,type='settlement',body='SPC test-token collateral settled in one atomic XRPL Batch.',data={'hash':result['hash'],'network':network,'plan':plan}))
        def failed(session,unknown,message):
            current=session.get(XRPLSettlement,squad_id); current.status='unknown' if unknown else 'releasing'; current.message=message
        self._run(f'payout:{squad_id}',request,[sender_id,*[f'member:{network}:{member}' for member in members]],done,squad_id=squad_id,user_id=user_id,failed=failed)
        return self.detail(squad_id,user_id)

    def _finish(self,squad_id,user_id,member_id):
        with self.db() as session:
            escrow=session.scalar(select(XRPLEscrow).where(XRPLEscrow.squad_id==squad_id,XRPLEscrow.user_id==member_id))
            if escrow.status=='released': return
            if escrow.status!='locked': raise HTTPException(409,'Escrow cannot be released until its previous operation is reconciled.')
            settlement=session.get(XRPLSettlement,squad_id); sender=session.get(XRPLWallet,settlement.wallet_id)
            request={'operation':'escrow-finish','encrypted_seed':sender.encrypted_seed,'owner':escrow.owner,'offer_sequence':escrow.offer_sequence,'condition':escrow.condition,'encrypted_fulfillment':escrow.encrypted_fulfillment}
            escrow_id=escrow.id; sender_id=sender.id
        def done(session,result):
            escrow=session.get(XRPLEscrow,escrow_id); escrow.status='released'; escrow.finish_hash=result['hash']
        def failed(session,unknown,message):
            session.get(XRPLEscrow,escrow_id).status='unknown' if unknown else 'locked'
            current=session.get(XRPLSettlement,squad_id); current.status='unknown' if unknown else 'releasing'; current.message=message
        def prepare(session):
            escrow=session.get(XRPLEscrow,escrow_id)
            current=session.get(XRPLSettlement,squad_id)
            if escrow.status!='locked' or current.status!='releasing': raise HTTPException(409,'Escrow state changed before its release.')
            escrow.status='releasing'
        self._run(f'finish:{escrow_id}',request,[sender_id,f'escrow:{escrow_id}'],done,squad_id=squad_id,user_id=user_id,failed=failed,prepare=prepare)

    def refund(self,squad_id,user_id):
        self.ready()
        with self.db() as session:
            self.squad(session,squad_id,user_id)
            settlement=session.get(XRPLSettlement,squad_id)
            escrow=session.scalar(select(XRPLEscrow).where(XRPLEscrow.squad_id==squad_id,XRPLEscrow.user_id==user_id))
            if not escrow: raise HTTPException(409,'This member has no locked escrow.')
            if escrow.status=='refunded': return squad_xrpl_detail(session,squad_id)
            if escrow.status!='locked' or not settlement or settlement.status in ['releasing','settled','unknown']:
                raise HTTPException(409,'Only a confirmed locked escrow can be canceled. Released or uncertain collateral requires reconciliation.')
            sender=session.get(XRPLWallet,escrow.wallet_id); escrow_id=escrow.id; wallet_id=sender.id
            request={'operation':'escrow-cancel','encrypted_seed':sender.encrypted_seed,'owner':escrow.owner,'offer_sequence':escrow.offer_sequence}
            cancel_after=escrow.cancel_after
        status=self.read('probe')['status']
        if status.get('ledger_close_time',0)<=cancel_after: raise HTTPException(409,'Refund becomes available after the CancelAfter deadline in validated ledger time. It requires a real EscrowCancel transaction.')
        def done(session,result):
            escrow=session.get(XRPLEscrow,escrow_id); escrow.status='refunded'; escrow.cancel_hash=result['hash']
            rows=session.scalars(select(XRPLEscrow).where(XRPLEscrow.squad_id==squad_id)).all()
            current=session.get(XRPLSettlement,squad_id); current.status='refunded' if all(row.status=='refunded' for row in rows) else 'refunding'
            session.add(SquadEvent(squad_id=squad_id,user_id=user_id,type='refund',body='Expired SPC test-token collateral refunded by an XRPL EscrowCancel.',data={'hash':result['hash'],'network':current.network}))
        def failed(session,unknown,message):
            session.get(XRPLEscrow,escrow_id).status='unknown' if unknown else 'locked'
            current=session.get(XRPLSettlement,squad_id); current.status='unknown' if unknown else 'refunding'; current.message=message
        def prepare(session):
            escrow=session.get(XRPLEscrow,escrow_id); current=session.get(XRPLSettlement,squad_id)
            if escrow.status!='locked' or current.status not in ['gathering','locked','refunding']: raise HTTPException(409,'Escrow or settlement state changed before cancellation.')
            escrow.status='refunding'; current.status='refunding'
        self._run(f'refund:{escrow_id}',request,[wallet_id,f'escrow:{escrow_id}'],done,squad_id=squad_id,user_id=user_id,failed=failed,prepare=prepare)
        return self.detail(squad_id,user_id)


def register_xrpl(app,engine,feed,executor=None):
    service=XRPLService(engine,feed,executor or execute_cli)
    app.state.xrpl_service=service

    @app.get('/xrpl/status')
    def status(): return service.status()

    @app.post('/xrpl/setup')
    def setup(payload:MemberInput): return service.setup(payload.user_id)

    @app.get('/xrpl/wallet')
    def get_wallet(user_id:str): return service.wallet(user_id)

    @app.post('/xrpl/wallet')
    def create_wallet(payload:MemberInput): return service.wallet(payload.user_id,create=True)

    @app.get('/squads/{squad_id}/xrpl')
    def detail(squad_id:str,user_id:str): return service.detail(squad_id,user_id)

    @app.post('/squads/{squad_id}/xrpl/lock')
    def lock(squad_id:str,payload:MemberInput): return service.lock(squad_id,payload.user_id)

    @app.post('/squads/{squad_id}/xrpl/settle')
    def settle(squad_id:str,payload:MemberInput): return service.settle(squad_id,payload.user_id)

    @app.post('/squads/{squad_id}/xrpl/refund')
    def refund(squad_id:str,payload:MemberInput): return service.refund(squad_id,payload.user_id)
