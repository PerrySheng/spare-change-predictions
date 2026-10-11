# Research swarm backend

The backend coordinates four independent Claude forecasting calls, four separate debate revisions, and one summary call. The final Yes probability is the application-computed median of the four revised estimates. For four numbers, that is the mean of the middle two. The summary model cannot replace the number.

This is research, not an order-placement bot. It has no trading tools or access to roundup funds. A stored Gemini buy quote is the comparison baseline; the displayed gap does not account for fees and does not guarantee profit.

## Run and configure

```sh
cd swarm
npm ci
npm run build
npm test
cd ..
.venv/bin/python -m pytest -q -c backend/pytest.ini backend/tests/test_swarm.py
```

Set `ANTHROPIC_API_KEY` in the server's `.env`. `ANTHROPIC_MODEL` defaults to `claude-sonnet-5-5`, documented in the [current model catalog](https://platform.claude.com/docs/en/models/overview). The worker queries the actual Models API for account access and web-search/thinking capabilities before any paid Messages call. Model access and web-search permission must be available on that account. An optional `SWARM_NODE_BIN` points to a Node executable if it is absent from the server PATH. Restart the backend after changing environment settings.

The worker uses pinned `@anthropic-ai/sdk` version `0.133.0`, verified against the published official SDK and installed types on October 11, 2026. The application integration imports `swarm_models` before `build_engine`, then calls `register_swarm(app, engine, feed, reading)`. This returns the service and sets `app.state.swarm`. Existing lifespan cleanup is preserved.

## Endpoint and stream contract

| Endpoint | Behavior |
| --- | --- |
| `POST /swarm/run` | Body `{user_id, market_id, outcome: "yes" or "no"}`. Fresh open-market validation; returns `{id, run_id, status, cached}`. |
| `GET /swarm/runs/{id}?user_id=...` | Returns the market snapshot, persisted public events, both rounds of estimates, final result if complete, provider usage, and failure information. |
| `GET /swarm/runs/{id}/stream?user_id=...&after=...` | SSE replays persisted IDs after the cursor, then emits new persisted events. Supports `Last-Event-ID`, sends heartbeats, and closes after terminal events. |
| `GET /swarm/markets/{market_id}?user_id=...&outcome=...` | Returns `{run: ...}` for that user's completed, fresh cached run, or `{run: null}`. Outcome filtering is optional. |
| `GET /swarm/metrics?user_id=...` | Refreshes actual Gemini resolutions and returns prospective forecast counts, Brier score, side edge, and void/sample counts. |

Run reads, cache reads, and SSE are restricted to the supplied user. An explicitly shared completed run also has a separate squad-member route; see [Phase D connections](SWARM_CONNECTIONS.md). This MVP's existing user-ID mechanism is not a production authentication system.

Every SSE message uses its persisted integer as `id`, its event type as the SSE `event` name, and JSON `{id, type, data, created_at}` as `data`. Supported public events are `agent_started`, `search_query`, `source_found`, `evidence_note`, `estimate_submitted`, `estimate_revised`, `round_changed`, `final_result`, and `error`. The complete event list is also returned by the run GET, so replay never requires a new paid call.

The final result contains `probability` (Yes), `outcome`, `selected_probability`, recorded `market_price`, `gap`, `summary`, three `reasons`, `disagreements`, the four-agent `range`, and observed `sources`. Python rechecks the median and derives the price/gap from its immutable snapshot. Incomplete estimates or a market closing before completion prevent a completed prospective forecast.

## Sources and public evidence

News Scout, Base Rate Analyst, and Skeptic can receive the documented [basic web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool), `web_search_20250305`, with `max_uses: 2`. The tool is omitted when fresh shared evidence is already present. Market Reader receives only the verified Gemini snapshot and no search tool; missing price history remains unavailable. The debate and Synthesizer calls have no search tool.

The [official streaming contract](https://platform.claude.com/docs/en/build-with-claude/streaming) provides visible text deltas, server-tool input JSON, search-result blocks, and citations. The worker collects partial search JSON until block completion, then emits the actual query. Search URLs/titles and citation excerpts come from those actual response blocks. It never decrypts search result content or invents article text. Citation/source URLs must have been observed in provider output or supplied public evidence before an estimate can use them.

`evidence_note` carries normal visible response text before the final estimate JSON. Thinking, signatures, redacted thinking, and encrypted search content never enter the public event log. Stored sources preserve observed URLs/titles/excerpts and link to originals; they are not guaranteed to prove a forecast.

`cache_sources(engine, market_id, sources, provider)` stores safe public `{url,title,snippet}` metadata. `cached_sources(engine, market_id)` returns fresh rows from the last 30 minutes, without any network request. News and the swarm share these rows. If the cache is empty and a Context.dev key exists, the swarm can use `reading.materials` with only the public market title and label. If its key is absent, no Context.dev request is made. Actual Anthropic `source_found` events are saved into the same cache. This does not intercept or deduplicate arbitrary native Anthropic search queries.

## Limits and failure behavior

- At most two new jobs per user per hour and two active jobs globally. Failed provider attempts count toward the hourly cap; missing-key requests create no job or progress events.
- Exact user/market/outcome jobs deduplicate atomically. Completed results are cached for 30 minutes. Public source metadata can be shared across users, but private run IDs are not.
- Nine Messages calls maximum, 1,800 output tokens per call, no SDK automatic retries, no new searches in debate. The worker has a ten-minute process deadline and is terminated on shutdown.
- The Python bridge persists each validated event before SSE can expose it. Invalid JSON, out-of-range probability, bad citations, unsupported event types, missing agents, or a wrong median fail the run instead of manufacturing output.
- Server restart marks queued/running jobs failed. Completed logs remain readable. A failed run may contain real partial events and measured usage, while its result remains absent.
- Token/cache/search counters come from actual provider usage messages, including available partial stream usage. They are measured counters, not a dollar-cost estimate. Usage that the provider never reports is unavailable.

The existing SQLite/WAL database is intended for one backend process. Recovery on startup assumes a prior local process was interrupted; do not run multiple independent backend instances against the same SQLite file.

## Prospective scoring

Every completed forecast retains its original market snapshot and both buy quotes when genuinely available. `refresh_swarm_forecasts(engine, feed)` reads actual event resolutions. For non-void results, Brier score is `(p_yes - resolved_yes)^2`. Forecast side is Yes when `p_yes >= 0.5`, otherwise No; side edge is `hit - that_side_buy_quote_at_forecast`. Missing counterpart quotes make that edge unavailable rather than inferred. Voids are separate and excluded from win/loss and score averages. A `scored_at` guard prevents double scoring.

## Verified results and remaining live check

The TypeScript build and five controlled stream/schema tests pass. Twenty-seven focused Python tests pass for missing-key boundaries, account isolation, cache/dedup/rate limits, SSE replay IDs, quote/median integrity, schema rejection, source reuse, allowed search rounds, restart handling, and one-time scoring. Controlled worker estimates live only in tests and are never seeded into the application.

A direct launch of the built worker without credentials returned only `Set ANTHROPIC_API_KEY in the server .env to run the research swarm.` and exited 1. No Anthropic API key is configured, so model access, real research events, two actual market forecasts, differing provider results, and live browser streaming remain unverified. Do not label that live self-check complete until credentials are configured and two actual runs are recorded.
