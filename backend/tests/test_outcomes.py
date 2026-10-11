from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Pot
from app.main import create_app
from app.scoring import rank_markets
from test_api import MarketFeed, purchase, user
from test_logic import NOW, market


def side(symbol, outcome, price, **details):
    return {**market(symbol, 'sports', price), 'outcome': outcome, **details}


def test_contract_outcomes_keep_provider_prices_and_independent_quotes():
    rows = [side('contract', 'no', '.70'), side('contract', 'yes', '.20')]
    result = rank_markets(rows, ['sports'], [], [], 99, now=NOW)
    assert len(result) == 1
    assert result[0]['outcome'] == 'yes'
    assert result[0]['price'] == '.20'
    assert result[0]['quote'] == {
        'quantity': 4, 'cost_cents': 80, 'fee_cents': 5,
        'total_cents': 85, 'leftover_cents': 14,
    }
    assert result[0]['outcomes'] == [
        {
            'outcome': 'yes', 'price': '.20', 'selectable': True, 'reason': None,
            'quote': {'quantity': 4, 'cost_cents': 80, 'fee_cents': 5,
                      'total_cents': 85, 'leftover_cents': 14},
        },
        {
            'outcome': 'no', 'price': '.70', 'selectable': True, 'reason': None,
            'quote': {'quantity': 1, 'cost_cents': 70, 'fee_cents': 2,
                      'total_cents': 72, 'leftover_cents': 27},
        },
    ]


def test_outcomes_are_grouped_by_instrument_not_shared_event():
    rows = [
        side('first-contract', 'yes', '.20', event_ticker='shared'),
        side('other-contract', 'no', '.80', event_ticker='shared'),
        side('first-contract', 'no', '.30', event_ticker='shared'),
    ]
    result = rank_markets(rows, ['sports'], [], [], 50, now=NOW)
    assert len(result) == 1
    assert result[0]['id'] == 'first-contract'
    assert [(s['outcome'], s['price']) for s in result[0]['outcomes']] == [
        ('yes', '.20'), ('no', '.30'),
    ]


def test_duplicate_rows_use_one_consistent_price_and_status_snapshot():
    rows = [
        side('contract', 'yes', '.10', status='resolved'),
        side('contract', 'yes', '.90', status='active'),
    ]
    result = rank_markets(rows, ['sports'], [], [], 99, now=NOW)[0]
    assert result['status'] == 'active' and result['price'] == '.90'
    assert result['quote']['cost_cents'] == 90 and result['quote']['total_cents'] == 91
    assert result['outcomes'][0]['price'] == '.90'


def test_missing_outcome_is_unavailable_without_a_complementary_price():
    result = rank_markets([side('contract', 'no', '.30')], [], [], [], 50, now=NOW)[0]
    assert result['outcome'] == 'no'
    assert result['outcomes'][0] == {
        'outcome': 'yes', 'price': None, 'quote': None,
        'selectable': False, 'reason': 'unavailable',
    }
    assert result['outcomes'][1]['selectable'] is True


@pytest.mark.parametrize('price', [None, 'NaN', 'not-a-price', '0', '1', '-.20', 'Infinity'])
def test_invalid_outcome_price_is_unavailable(price):
    result = rank_markets(
        [side('contract', 'yes', '.20'), side('contract', 'no', price)],
        [], [], [], 50, now=NOW,
    )[0]
    assert result['outcomes'][1] == {
        'outcome': 'no', 'price': None, 'quote': None,
        'selectable': False, 'reason': 'unavailable',
    }


@pytest.mark.parametrize('details', [
    {'status': 'resolved'},
    {'market_state': 'closed'},
    {'closes_at': (NOW - timedelta(seconds=1)).isoformat()},
    {'closes_at': None},
])
def test_closed_or_undated_outcome_has_no_executable_quote(details):
    result = rank_markets(
        [side('contract', 'yes', '.20'), side('contract', 'no', '.70', **details)],
        [], [], [], 99, now=NOW,
    )[0]
    assert result['outcomes'][1] == {
        'outcome': 'no', 'price': '.70', 'quote': None,
        'selectable': False, 'reason': 'unavailable',
    }


def test_unaffordable_side_keeps_its_real_price_and_zero_quantity_quote():
    result = rank_markets(
        [side('contract', 'yes', '.20'), side('contract', 'no', '.70')],
        [], [], [], 50, now=NOW,
    )[0]
    assert result['outcomes'][1] == {
        'outcome': 'no', 'price': '.70', 'selectable': False, 'reason': 'unaffordable',
        'quote': {'quantity': 0, 'cost_cents': 0, 'fee_cents': 0,
                  'total_cents': 0, 'leftover_cents': 50},
    }


@pytest.mark.parametrize('details', [
    {'status': 'invalid'},
    {'market_state': 'closed'},
    {'closes_at': (NOW - timedelta(seconds=1)).isoformat()},
])
def test_unavailable_contracts_do_not_become_recommendations(details):
    assert rank_markets(
        [side('contract', 'yes', '.20', **details)], [], [], [], 99, now=NOW,
    ) == []


class TwoOutcomeFeed(MarketFeed):
    def markets(self):
        yes = super().markets()[0]
        return [yes, {**yes, 'outcome': 'no', 'price': '.70', 'sell_price': '.65'}]

    def market(self, symbol, outcome):
        return next(m for m in self.markets() if m['id'] == symbol and m['outcome'] == outcome)


def test_api_allocates_no_at_its_own_price_with_confirmed_quantity_and_cost(tmp_path):
    app = create_app('sqlite:///' + str(tmp_path / 'outcomes.db'), feed=TwoOutcomeFeed(), mode='paper')
    with TestClient(app) as client:
        user_id = user(client, cap=1000)
        pending = purchase(client, user_id, '4.01')
        recommended = client.get('/suggestions', params={
            'user_id': user_id, 'roundup_id': pending['roundup_id'],
        }).json()['markets'][0]
        no = recommended['outcomes'][1]
        assert no['outcome'] == 'no' and no['price'] == '.70'
        assert no['quote']['quantity'] == 1 and no['quote']['total_cents'] == 72
        with Session(app.state.engine) as session:
            session.get(Pot, user_id).rollover_cents = 400
            session.commit()
        response = client.post('/roundups/' + pending['roundup_id'] + '/allocate', json={
            'user_id': user_id, 'destination': 'market', 'market_id': recommended['id'],
            'outcome': no['outcome'], 'max_price': no['price'],
            'max_quantity': no['quote']['quantity'], 'max_total_cents': no['quote']['total_cents'],
        })
        assert response.status_code == 200, response.text
        dashboard = client.get('/dashboard', params={'user_id': user_id}).json()
        position = dashboard['positions'][0]
        assert position['outcome'] == 'no' and position['entry_price'] == '0.70'
        assert position['quantity'] == 1 and position['cost_cents'] == 70 and position['fee_cents'] == 2
        assert dashboard['weekly_spent_cents'] == 72 and dashboard['rollover_cents'] == 427
