import json

import httpx
import pytest

from app.context_reading import ContextReading
from app.providers import ProviderError


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('CONTEXT_DEV_API_KEY', 'test-context-key')
    return ContextReading()


def use_http(monkeypatch, handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr('app.context_reading.httpx.stream', client.stream)
    return client


def test_missing_key_is_actionable_and_sends_no_request(monkeypatch):
    monkeypatch.delenv('CONTEXT_DEV_API_KEY', raising=False)
    with use_http(monkeypatch, lambda request: pytest.fail('No request without a key')):
        with pytest.raises(ProviderError, match='CONTEXT_DEV_API_KEY'):
            ContextReading().materials('Will it rain?', 'New York')


def test_search_uses_documented_contract_and_only_public_market_text(provider, monkeypatch):
    def handler(request):
        assert request.method == 'POST'
        assert str(request.url) == 'https://api.context.dev/v1/web/search'
        assert request.headers['Authorization'] == 'Bearer test-context-key'
        assert json.loads(request.content) == {'query': 'Will it rain? New York', 'numResults': 10}
        return httpx.Response(200, json={
            'results': [{'url': 'https://weather.example/forecast', 'title': 'Weather forecast',
                         'description': 'Public forecast details', 'relevance': 'high'}],
            'query': 'Will it rain? New York', 'request_id': 'test-request', 'partial': True,
            'key_metadata': {'credits_consumed': 1, 'credits_remaining': 99},
        })

    with use_http(monkeypatch, handler):
        result = provider.materials(' Will it rain?\n', 'New York')
    assert result['sources'] == [{'url': 'https://weather.example/forecast',
                                 'title': 'Weather forecast', 'snippet': 'Public forecast details'}]
    assert result['provider'] == 'Context.dev'
    assert result['query'] == 'Will it rain? New York'
    assert result['partial'] is True and result['cached'] is False
    assert 'key_metadata' not in result and 'test-context-key' not in json.dumps(result)


def test_filters_unsafe_links_deduplicates_and_bounds_returned_sources(provider, monkeypatch):
    unsafe = ['javascript:alert(1)', 'data:text/html,a', 'file:///etc/passwd', '//example.com',
              'https://user:password@example.com', 'https://example.com:bad/path',
              'https://exa mple.com', 'https://example.com/\nscript']
    rows = [{'url': url, 'title': 'Unsafe', 'description': 'Discard'} for url in unsafe]
    rows += [{'url': 'https://example.com/first', 'title': 'T' * 1000, 'description': 'S' * 2000}] * 2
    rows += [{'url': f'http://example.com/{i}', 'title': f'Page {i}', 'description': 'Reading'} for i in range(20)]
    rows += [None, {'url': 'https://example.com/' + 'x' * 3000}]
    with use_http(monkeypatch, lambda request: httpx.Response(200, json={'results': rows})):
        sources = provider.materials('Public market')['sources']
    assert len(sources) == 5
    assert sources[0] == {'url': 'https://example.com/first', 'title': 'T' * 200, 'snippet': 'S' * 500}
    assert sources[1]['url'] == 'http://example.com/0'
    assert len({s['url'] for s in sources}) == 5


def test_query_keeps_both_fields_and_stays_within_provider_limit(provider, monkeypatch):
    def handler(request):
        query = json.loads(request.content)['query']
        assert len(query) <= 500
        assert 'Public label' in query
        return httpx.Response(200, json={'results': []})
    with use_http(monkeypatch, handler):
        assert provider.materials('T' * 2000, 'Public label')['sources'] == []


def test_cache_reuses_for_ten_minutes_then_refreshes(provider, monkeypatch):
    now = [100.0]
    calls = []
    monkeypatch.setattr('app.context_reading.time.monotonic', lambda: now[0])
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'results': [{'url': 'https://example.com',
            'title': f'Version {len(calls)}', 'description': 'Public detail'}]})
    with use_http(monkeypatch, handler):
        first = provider.materials('Public market')
        first['sources'][0]['title'] = 'Client mutated response'
        now[0] = 699.0
        cached = provider.materials('Public market')
        assert cached['cached'] is True
        assert cached['sources'][0]['title'] == 'Version 1'
        now[0] = 700.0
        refreshed = provider.materials('Public market')
        assert refreshed['cached'] is False
        assert refreshed['sources'][0]['title'] == 'Version 2'
    assert len(calls) == 2


def test_cached_results_still_require_server_configuration(provider, monkeypatch):
    with use_http(monkeypatch, lambda request: httpx.Response(200, json={'results': []})):
        provider.materials('Public market')
    monkeypatch.delenv('CONTEXT_DEV_API_KEY', raising=False)
    with use_http(monkeypatch, lambda request: pytest.fail('No request without a key')):
        with pytest.raises(ProviderError, match='CONTEXT_DEV_API_KEY'):
            provider.materials('Public market')


def test_cache_evicts_oldest_public_query(provider, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'results': []})
    with use_http(monkeypatch, handler):
        for i in range(129):
            provider.materials(f'Public market {i}')
        assert provider.materials('Public market 128')['cached'] is True
        assert provider.materials('Public market 0')['cached'] is False
    assert len(calls) == 130


@pytest.mark.parametrize('status, expected', [(401, 'API key'), (403, 'API key'),
                                            (429, 'busy'), (408, 'timed out'), (500, 'unavailable')])
def test_provider_errors_are_clean_and_not_cached(provider, monkeypatch, status, expected):
    def handler(request):
        return httpx.Response(status, json={'message': 'sensitive upstream details test-context-key'})
    with use_http(monkeypatch, handler):
        with pytest.raises(ProviderError, match=expected) as exc:
            provider.materials('Public market')
    assert 'sensitive' not in str(exc.value) and 'test-context-key' not in str(exc.value)
    with use_http(monkeypatch, lambda request: httpx.Response(200, json={'results': []})):
        assert provider.materials('Public market')['cached'] is False


def test_timeout_becomes_readable_unavailable_error(provider, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout('private transport details', request=request)
    with use_http(monkeypatch, handler):
        with pytest.raises(ProviderError, match='timed out'):
            provider.materials('Public market')


@pytest.mark.parametrize('body', [b'not json', b'[]', b'{"results":{}}', b'{}', b'x' * 300000])
def test_malformed_or_oversized_responses_fail_cleanly(provider, monkeypatch, body):
    with use_http(monkeypatch, lambda request: httpx.Response(200, content=body)):
        with pytest.raises(ProviderError, match='invalid|too large'):
            provider.materials('Public market')


def test_blank_public_market_text_does_not_send_a_request(provider, monkeypatch):
    with use_http(monkeypatch, lambda request: pytest.fail('Blank query must not be sent')):
        with pytest.raises(ProviderError, match='market title'):
            provider.materials(' \n ', '')
