"""Event browsing and selected budgets exercise the real API accounting."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers import ProviderError
from test_api import MarketFeed, purchase, user


class SelectionFeed(MarketFeed):
    def __init__(self):
        super().__init__()
        self.price = '.40'
        self.rows = None

    def markets(self):
        if self.failed:
            raise ProviderError('Gemini unavailable')
        if self.rows is not None:
            return self.rows
        yes = super().markets()[0]
        return [yes, {**yes, 'outcome': 'no', 'price': '.65'}]

    def market(self, symbol, outcome):
        return next(row for row in self.markets()
                    if row['id'] == symbol and row['outcome'] == outcome)


@pytest.fixture
def selection(tmp_path):
    feed = SelectionFeed()
    with TestClient(create_app('sqlite:///' + str(tmp_path / 'selection.db'),
                              feed=feed, mode='paper')) as client:
        yield client, feed


def catalog_rows(feed):
    base = feed.markets()[0]
    rows = []
    for event, title, category, symbol, label, yes, no in [
        ('BINARY', 'Will the launch succeed?', 'Science', 'GEMI-LAUNCH', 'Launch succeeds', '.4100', '.66'),
        ('ELECTION', 'Who wins the election?', 'Politics', 'GEMI-ASTER', 'Aster', '.20', '.83'),
        ('ELECTION', 'Who wins the election?', 'Politics', 'GEMI-BIRCH', 'Birch', '.6100', '.43'),
        ('ELECTION', 'Who wins the election?', 'Politics', 'GEMI-CEDAR', 'Cedar', '.18', '.85'),
        ('ELECTION', 'Who wins the election?', 'Politics', 'GEMI-DOGWOOD', 'Dogwood', None, '.91'),
    ]:
        for outcome, price in [('yes', yes), ('no', no)]:
            if price is None:
                continue
            rows.append({**base, 'id': symbol, 'event_ticker': event,
                         'title': title, 'category': category, 'topic': category.lower(),
                         'label': label, 'outcome': outcome, 'price': price,
                         'market_state': 'open', 'terms_url': 'https://www.gemini.com/predictions'})
    return rows


def test_catalog_groups_binary_sides_into_one_real_contract(selection):
    client, feed = selection
    feed.rows = catalog_rows(feed)
    response = client.get('/markets/events')
    assert response.status_code == 200, response.text
    assert response.headers['content-type'].startswith('application/json')
    result = response.json()
    assert result['source'] == 'gemini'
    event = next(event for event in result['events'] if event['id'] == 'BINARY')
    assert event['title'] == 'Will the launch succeed?' and event['category'] == 'Science'
    assert event['source'] == 'gemini' and event['closes_at']
    assert len(event['outcomes']) == 1
    contract = event['outcomes'][0]
    assert contract['id'] == 'GEMI-LAUNCH' and contract['event_ticker'] == 'BINARY'
    assert contract['label'] == 'Launch succeeds' and contract['title'] == event['title']
    assert contract['prices'] == {'yes': '.4100', 'no': '.66'}
    assert contract['implied_probability'] == .41
    assert contract['status'] == 'active' and contract['market_state'] == 'open'
    assert contract['quantity_minimum'] == '1' and contract['quantity_increment'] == '1'


def test_catalog_orders_multiple_contracts_by_yes_price_with_missing_last(selection):
    client, feed = selection
    feed.rows = catalog_rows(feed)
    response = client.get('/markets/events')
    assert response.status_code == 200, response.text
    event = next(event for event in response.json()['events'] if event['id'] == 'ELECTION')
    assert [contract['id'] for contract in event['outcomes']] == [
        'GEMI-BIRCH', 'GEMI-ASTER', 'GEMI-CEDAR', 'GEMI-DOGWOOD',
    ]
    assert [contract['implied_probability'] for contract in event['outcomes']] == [.61, .2, .18, None]
    assert event['outcomes'][-1]['prices'] == {'yes': None, 'no': '.91'}


@pytest.mark.parametrize('query', [' aStEr ', 'POLITICS', 'election'])
def test_catalog_search_retains_all_contracts_of_matching_event(selection, query):
    client, feed = selection
    feed.rows = catalog_rows(feed)
    response = client.get('/markets/events', params={'query': query})
    assert response.status_code == 200, response.text
    events = response.json()['events']
    assert [event['id'] for event in events] == ['ELECTION']
    assert len(events[0]['outcomes']) == 4


def test_catalog_empty_or_failed_feed_has_no_fixture_fallback(selection):
    client, feed = selection
    feed.rows = []
    response = client.get('/markets/events')
    assert response.status_code == 200, response.text
    assert response.json() == {'events': [], 'source': 'gemini'}
    feed.failed = True
    assert client.get('/markets/events').status_code == 503


def test_suggestions_include_complete_events_without_changing_side_choices(selection):
    client, feed = selection
    feed.rows = [row for row in catalog_rows(feed) if row['event_ticker'] == 'ELECTION']
    user_id = user(client)
    pending = purchase(client, user_id, '4.01')
    response = client.get('/suggestions', params={'user_id': user_id,
                                                  'roundup_id': pending['roundup_id']})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result['markets']) == 1
    assert [side['outcome'] for side in result['markets'][0]['outcomes']] == ['yes', 'no']
    assert [event['id'] for event in result['events']] == ['ELECTION']
    assert len(result['events'][0]['outcomes']) == 4
    assert result['events'][0]['why'] == result['markets'][0]['why']
    client.patch('/users/' + user_id, json={'paused': True})
    assert client.get('/suggestions', params={'user_id': user_id,
                                             'roundup_id': pending['roundup_id']}).json()['events'] == []


def test_suggestion_events_deduplicate_repeated_event_recommendations(selection, monkeypatch):
    client, feed = selection
    feed.rows = catalog_rows(feed)
    user_id = user(client)
    pending = purchase(client, user_id, '4.01')
    # The catalog boundary also tolerates a future ranker choosing several
    # contracts from one event; retain its first recommendation and why.
    monkeypatch.setattr('app.main.rank_markets', lambda *args: [
        {'id': 'GEMI-BIRCH', 'event_ticker': 'ELECTION', 'why': 'First ranked choice'},
        {'id': 'GEMI-ASTER', 'event_ticker': 'ELECTION', 'why': 'Another contract'},
        {'id': 'GEMI-LAUNCH', 'event_ticker': 'BINARY', 'why': 'A different event'},
    ])
    response = client.get('/suggestions', params={'user_id': user_id,
                                                 'roundup_id': pending['roundup_id']})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result['markets']) == 3
    assert [event['id'] for event in result['events']] == ['ELECTION', 'BINARY']
    assert result['events'][0]['why'] == 'First ranked choice'
    assert len(result['events'][0]['outcomes']) == 4


def quote_params(user_id, pending, **extra):
    return {'user_id': user_id, 'roundup_id': pending['roundup_id'],
            'market_id': 'GEMI-TEST-A', **extra}


def allocation_payload(user_id, **extra):
    return {'user_id': user_id, 'destination': 'market',
            'market_id': 'GEMI-TEST-A', **extra}


def test_selected_amount_caps_quote_and_leaves_all_unspent_funds_in_rollover(selection):
    client, _ = selection
    user_id = user(client, cap=1000)
    held = purchase(client, user_id, '4.63')
    assert client.post('/roundups/' + held['roundup_id'] + '/allocate', json={
        'user_id': user_id, 'destination': 'rollover',
    }).status_code == 200
    pending = purchase(client, user_id, '4.01')
    response = client.get('/markets/quote', params=quote_params(user_id, pending, amount_cents=83))
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview['budget_cents'] == 83
    assert preview['available_cents'] == 136 and 'remaining_cap_cents' not in preview
    assert preview['quote'] == {'quantity': 1, 'cost_cents': 40, 'fee_cents': 2,
                               'total_cents': 42, 'leftover_cents': 41}
    response = client.post('/roundups/' + pending['roundup_id'] + '/allocate',
                           json=allocation_payload(user_id, amount_cents=83))
    assert response.status_code == 200, response.text
    dashboard = client.get('/dashboard', params={'user_id': user_id}).json()
    assert dashboard['weekly_spent_cents'] == 42 and dashboard['rollover_cents'] == 94
    assert dashboard['positions'][0]['quantity'] == 1
    assert dashboard['positions'][0]['cost_cents'] == 40 and dashboard['positions'][0]['fee_cents'] == 2


@pytest.mark.parametrize('amount', [100, 1000000])
def test_selected_amount_cannot_exceed_available_funds(selection, amount):
    client, _ = selection
    user_id = user(client, cap=0)
    pending = purchase(client, user_id, '4.01')
    assert client.get('/markets/quote', params=quote_params(user_id, pending, amount_cents=amount)).status_code == 409
    assert client.post('/roundups/' + pending['roundup_id'] + '/allocate',
                       json=allocation_payload(user_id, amount_cents=amount)).status_code == 409
    dashboard = client.get('/dashboard', params={'user_id': user_id}).json()
    assert dashboard['weekly_spent_cents'] == 0 and dashboard['pending_cents'] == 99


@pytest.mark.parametrize('amount', [0, -1, 1.5])
def test_selected_amount_requires_positive_whole_cents(selection, amount):
    client, _ = selection
    user_id = user(client)
    pending = purchase(client, user_id, '4.01')
    assert client.get('/markets/quote', params=quote_params(user_id, pending, amount_cents=amount)).status_code == 422
    assert client.post('/roundups/' + pending['roundup_id'] + '/allocate',
                       json=allocation_payload(user_id, amount_cents=amount)).status_code == 422


def test_selected_amount_cannot_bypass_contract_grid_or_confirmed_cost(selection):
    client, feed = selection
    user_id = user(client, cap=1000)
    pending = purchase(client, user_id, '4.01')
    rows = feed.markets()
    feed.rows = [{**row, 'quantity_increment': '2'} for row in rows]
    assert client.get('/markets/quote', params=quote_params(user_id, pending, amount_cents=83)).status_code == 409
    assert client.post('/roundups/' + pending['roundup_id'] + '/allocate',
                       json=allocation_payload(user_id, amount_cents=83)).status_code == 409
    response = client.get('/markets/quote', params=quote_params(user_id, pending, amount_cents=84))
    assert response.status_code == 200, response.text
    assert response.json()['quote']['quantity'] == 2 and response.json()['quote']['total_cents'] == 84
    response = client.post('/roundups/' + pending['roundup_id'] + '/allocate',
                           json=allocation_payload(user_id, amount_cents=99,
                                                   max_quantity=2, max_total_cents=83))
    assert response.status_code == 409
