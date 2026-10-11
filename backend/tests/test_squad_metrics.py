import pytest
from app.squad_metrics import track_record, payout_plan


def leg(status, price='.5', category='sports', date='2026-10-01T00:00:00+00:00', **extra):
    return {'status': status, 'entry_price': price, 'category': category, 'resolved_at': date, **extra}


def test_empty_record_does_not_invent_accuracy():
    record = track_record([])
    assert record['wins'] == record['losses'] == record['void'] == record['pending'] == 0
    assert record['hit_rate'] is None and record['edge_score'] is None
    assert record['disagree_accuracy'] is None and record['swarm_comparison'] is None


def test_record_edge_categories_streak_and_void():
    record = track_record([
        leg('won', '.2'), leg('lost', '.7', 'crypto', '2026-10-02T00:00:00+00:00'),
        leg('lost', '.4', 'sports', '2026-10-03T00:00:00+00:00'), leg('void', '.9'),
        leg('open'), leg('won', '.1', active=False), leg('won', '.1', locked=False),
    ])
    assert (record['wins'], record['losses'], record['void'], record['pending']) == (1, 2, 1, 1)
    assert record['hit_rate'] == pytest.approx(1 / 3)
    assert record['edge_score'] == pytest.approx(-.1)
    assert record['categories']['sports']['edge_score'] == pytest.approx(.2)
    assert record['streak'] == {'kind': 'loss', 'count': 2, 'label': '2 losses'}
    assert len(record['edge_over_time']) == 3


def test_disagree_accuracy_excludes_void_and_unresolved():
    votes = [{'reaction': 'disagree', 'leg': leg(s)} for s in ['lost', 'won', 'void', 'open']]
    votes += [{'reaction': 'agree', 'leg': leg('lost')}]
    record = track_record([], votes)
    assert record['disagree_accuracy'] == .5
    assert record['disagree_count'] == 2 and record['disagree_correct'] == 1


@pytest.mark.parametrize('losers,expected', [(['a'], [0, 1500, 1500]), (['a', 'b'], [750, 750, 1500]), ([], [1000, 1000, 1000]), (['a', 'b', 'c'], [1000, 1000, 1000])])
def test_payout_examples(losers, expected):
    plan = payout_plan(1500, ['a', 'b', 'c'], losers)
    assert [m['payout_cents'] for m in plan['members']] == expected
    assert plan['total_payout_cents'] == plan['total_collateral_cents'] == 3000


def test_odd_cents_conserved_deterministically():
    first = payout_plan(1501, ['c', 'a', 'b'], ['a', 'b'])
    second = payout_plan(1501, ['a', 'b', 'c'], ['b', 'a'])
    assert first == second
    assert sum(m['base_share_cents'] for m in first['members']) == 1501
    assert first['total_payout_cents'] == first['total_collateral_cents'] == 3002
    assert min(m['payout_cents'] for m in first['members']) >= 0


def test_invalid_payout_inputs_rejected():
    for stake, members, losers in [(0, ['a', 'b'], []), (1500, ['a', 'a'], []), (1500, ['a', 'b'], ['x'])]:
        with pytest.raises(ValueError): payout_plan(stake, members, losers)


def test_payout_conservation_for_all_supported_squad_sizes_and_rounding():
    from itertools import combinations
    for size in range(2, 7):
        members = [str(index) for index in range(size)]
        for stake in [1, 2, 7, 1499, 1500, 1501]:
            for loser_count in range(size + 1):
                for losers in combinations(members, loser_count):
                    plan = payout_plan(stake, members, losers)
                    assert plan['total_payout_cents'] == plan['total_collateral_cents'] == stake * (size - 1)
                    assert min(row['payout_cents'] for row in plan['members']) >= 0
