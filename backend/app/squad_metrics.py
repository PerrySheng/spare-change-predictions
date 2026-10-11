"""Track records and hypothetical escrow accounting, computed from persisted facts."""
from decimal import Decimal


def _final(leg):
    return leg.get('active', True) and leg.get('locked', True) and leg.get('status') not in ['swapped', 'replaced']


def _edge(leg):
    return Decimal(1 if leg['status'] == 'won' else 0) - Decimal(str(leg['entry_price']))


def _summary(legs):
    wins = sum(leg['status'] == 'won' for leg in legs)
    losses = sum(leg['status'] == 'lost' for leg in legs)
    resolved = wins + losses
    scored = [leg for leg in legs if leg['status'] in ['won', 'lost']]
    return {'wins': wins, 'losses': losses, 'void': sum(leg['status'] == 'void' for leg in legs),
            'pending': sum(leg['status'] not in ['won', 'lost', 'void'] for leg in legs),
            'resolved': resolved, 'hit_rate': wins / resolved if resolved else None,
            'edge_score': float(sum((_edge(leg) for leg in scored), Decimal(0)) / resolved) if resolved else None}


def track_record(legs, votes=None):
    """Callers supply one user's final locked picks and that user's reactions.

    Swapped and unlocked picks are excluded. Vote dictionaries contain a `leg`
    dictionary so disagree accuracy uses the actual final outcome of that pick.
    No swarm exists in this app; its comparison remains unavailable.
    """
    legs = [leg for leg in legs if _final(leg)]
    record = _summary(legs)
    categories = {}
    for leg in legs:
        category = (leg.get('category') or 'other').lower()
        categories.setdefault(category, []).append(leg)
    record['categories'] = {category: _summary(rows) for category, rows in sorted(categories.items())}
    scored = sorted([leg for leg in legs if leg['status'] in ['won', 'lost']],
                    key=lambda leg: (leg.get('resolved_at') or leg.get('created_at') or '', leg.get('id', '')))
    streak = 0
    latest = scored[-1]['status'] if scored else None
    for leg in reversed(scored):
        if leg['status'] != latest: break
        streak += 1
    kind = {'won': 'win', 'lost': 'loss'}.get(latest)
    record['streak'] = {'kind': kind, 'count': streak,
                        'label': f"{streak} {'win' if kind == 'win' else 'loss'}{'' if streak == 1 else ('s' if kind == 'win' else 'es')}" if kind else 'No resolved picks'}
    running = Decimal(0)
    record['edge_over_time'] = []
    for index, leg in enumerate(scored, 1):
        running += _edge(leg)
        record['edge_over_time'].append({'leg_id': leg.get('id'), 'at': leg.get('resolved_at') or leg.get('created_at'),
                                         'edge': float(_edge(leg)), 'average_edge': float(running / index)})
    disagreed = [vote['leg'] for vote in (votes or []) if vote.get('reaction') == 'disagree' and vote.get('leg')
                and _final(vote['leg']) and vote['leg'].get('status') in ['won', 'lost']]
    correct = sum(leg['status'] == 'lost' for leg in disagreed)
    record.update({'disagree_count': len(disagreed), 'disagree_correct': correct,
                   'disagree_accuracy': correct / len(disagreed) if disagreed else None,
                   'swarm_comparison': None})
    return record


def _split(total, member_ids):
    quotient, remainder = divmod(total, len(member_ids))
    return {member: quotient + (index < remainder) for index, member in enumerate(member_ids)}


def payout_plan(stake_cents, member_ids, loser_ids):
    """Exact-cent plan only; this function does not hold or transfer funds.

    Base shares and loser charges use sorted user IDs to assign rounding cents.
    That makes retries deterministic and keeps total payouts equal to collateral.
    """
    members = sorted(member_ids)
    losers = sorted(set(loser_ids))
    if type(stake_cents) is not int or stake_cents <= 0 or len(members) < 2 or len(members) != len(set(members)):
        raise ValueError('A positive integer stake and at least two distinct members are required.')
    if not set(losers).issubset(members): raise ValueError('Every loser must be a squad member.')
    shares = _split(stake_cents, members)
    collateral = {member: stake_cents - shares[member] for member in members}
    winners = [member for member in members if member not in losers]
    charges = _split(sum(shares[member] for member in winners), losers) if losers and winners else {}
    rows = []
    for member in members:
        owes = charges.get(member, 0)
        receives = shares[member] if charges and member in winners else 0
        rows.append({'user_id': member, 'base_share_cents': shares[member], 'collateral_cents': collateral[member],
                     'owes_cents': owes, 'receives_cents': receives, 'payout_cents': collateral[member] - owes + receives})
    return {'stake_cents': stake_cents, 'members': rows, 'total_collateral_cents': sum(collateral.values()),
            'total_payout_cents': sum(row['payout_cents'] for row in rows),
            'status': 'calculated', 'message': 'Calculated payout plan. No funds have been locked or transferred.'}
