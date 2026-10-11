"""Public market reading links from Context.dev, shared with Swarm research.

API contract: https://docs.context.dev/api-reference/web-scraping/search
Only Gemini's public title and label belong in ``materials``. User information,
purchase history, interests, market prices, and positions are never accepted.
"""

import copy
import json
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .providers import ProviderError


def _text(value, limit):
    return ' '.join(value.split())[:limit] if isinstance(value, str) else ''


def _safe_url(value):
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
            return None
        parts.port  # Reject invalid or out-of-range ports.
    except ValueError:
        return None
    return value


class ContextReading:
    """A bounded ten minute cache of public source metadata, shared by markets."""

    URL = 'https://api.context.dev/v1/web/search'
    CACHE_SECONDS = 600
    CACHE_ENTRIES = 128
    RESPONSE_BYTES = 256 * 1024

    def __init__(self):
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def materials(self, title: str, label: str = '') -> dict:
        key = (os.getenv('CONTEXT_DEV_API_KEY') or '').strip()
        if not key:
            raise ProviderError('Reading materials are unavailable. Set CONTEXT_DEV_API_KEY in the server .env and restart the backend.')
        if any(character.isspace() for character in key):
            raise ProviderError('Context.dev API key is invalid. Check CONTEXT_DEV_API_KEY in the server .env.')

        # Bound each public field independently so a long title cannot hide the label.
        query = ' '.join(dict.fromkeys(part for part in (_text(title, 350), _text(label, 140)) if part))
        if not query:
            raise ProviderError('Reading materials require a public market title or label.')

        with self._lock:
            cached = self._cache.get(query)
            if cached and time.monotonic() - cached[0] < self.CACHE_SECONDS:
                self._cache.move_to_end(query)
                return {**copy.deepcopy(cached[1]), 'cached': True}
            self._cache.pop(query, None)

        data = self._search(key, query)
        sources = []
        seen = set()
        for row in data['results'][:100]:
            if not isinstance(row, dict):
                continue
            url = _safe_url(row.get('url'))
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append({'url': url,
                            'title': _text(row.get('title'), 200) or urlsplit(url).hostname,
                            'snippet': _text(row.get('description'), 500)})
            if len(sources) == 5:
                break

        result = {'provider': 'Context.dev', 'query': query, 'sources': sources,
                  'fetched_at': datetime.now(timezone.utc).isoformat(), 'cached': False,
                  'partial': data.get('partial') is True}
        with self._lock:
            self._cache[query] = (time.monotonic(), copy.deepcopy(result))
            self._cache.move_to_end(query)
            while len(self._cache) > self.CACHE_ENTRIES:
                self._cache.popitem(last=False)
        return result

    def _search(self, key, query):
        try:
            # Search metadata only: no scraping, answer generation, or private inputs.
            # Context.dev documents a minimum of ten requested results; expose five.
            with httpx.stream('POST', self.URL,
                              headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                              json={'query': query, 'numResults': 10},
                              timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=False) as response:
                if response.status_code in (401, 403):
                    raise ProviderError('Context.dev API key was rejected. Check CONTEXT_DEV_API_KEY and its search permission.')
                if response.status_code == 429:
                    raise ProviderError('Context.dev is busy or its search limit was reached. Try again shortly.')
                if response.status_code in (408, 504):
                    raise ProviderError('Context.dev search timed out. Try again.')
                if not response.is_success:
                    raise ProviderError('Context.dev reading materials are temporarily unavailable. Try again.')
                content = bytearray()
                for chunk in response.iter_bytes():
                    if len(content) + len(chunk) > self.RESPONSE_BYTES:
                        raise ProviderError('Context.dev returned a response that is too large. Try again.')
                    content.extend(chunk)
                data = json.loads(content)
        except httpx.TimeoutException as exc:
            raise ProviderError('Context.dev search timed out. Try again.') from exc
        except httpx.HTTPError as exc:
            raise ProviderError('Context.dev is unreachable. Check the server connection and try again.') from exc
        except (ValueError, UnicodeError) as exc:
            raise ProviderError('Context.dev returned invalid reading material data. Try again.') from exc
        if not isinstance(data, dict) or not isinstance(data.get('results'), list):
            raise ProviderError('Context.dev returned invalid reading material data. Try again.')
        return data
