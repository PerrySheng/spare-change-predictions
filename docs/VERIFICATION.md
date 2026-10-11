# Verification record

Checked on October 11, 2026. Paper mode is enabled by default. Controlled provider fixtures are confined to tests; the application never returns sample forecasts, articles, markets, or transaction hashes.

| Check | Result |
| --- | --- |
| Python backend suite | **195 passed**. One existing Starlette TestClient/httpx deprecation warning. Includes master-key account routing and configuration guards. |
| Frontend production build | Passed with Vite 7.3.7. Swarm loads in a separate chunk; initial JS 316 kB before gzip. |
| Frontend event reducer | **4 Node tests passed**: real-event state transitions, revision/replay order, safe sources, changed-profile/market/side cache guards, and the News related-market component rendering without undefined props. Component rendering is a Node check, not a browser layout check. |
| Claude TypeScript worker | Build and **5 tests passed**: median, search-tool permissions, JSON/source validation, actual stream query parsing, public text versus hidden thinking. |
| XRPL TypeScript executor | TypeScript checks and **8 tests passed**: networks, crypto-condition, payout conservation, issued-token cents, atomic Batch flags, encryption. |
| Python dependencies / launch | `pip check`, `bash -n run.sh`, and Git whitespace checks passed. |
| Local server | `/health`, `/`, current built assets, manifest, service worker, and `/swarm/example` frontend route returned HTTP 200. OpenAPI confirms squads/news/swarm/quote/XRPL routes. |
| Live Gemini | Actual public production and sandbox market data retrieved; prior fee-aware Yes/No paper allocations verified. |
| Gemini sandbox authentication | Supplied credentials passed read-only account-list, balance, and prediction-terms checks. Master-key requests now include the configured account short name; the existing app preflight passed against Gemini. No order was submitted or filled; the server remains in paper mode. [Public check](GEMINI_AUTH_CHECK.json). |
| Digger personalization | Two new isolated profiles made actual paper allocations against live Gemini quotes. Sports history put sports first; crypto history put crypto first. [Raw check](NEWS_SELF_CHECK.json). |
| Shared research sources | Controlled tests prove News reuses persisted News Scout metadata without requiring another Context.dev call, and users/history/related instruments are scoped and computed. |
| Live Context.dev reading | With the supplied server-side key, an isolated profile requested an actual Gemini market through `/news/articles` and received five source links with bounded snippets. A second request returned the same source set from the shared cache without another provider call. The running server reports Context.dev configured. [Public check](CONTEXT_LIVE_CHECK.json). |
| Claude missing key | Live-market run requests returned actionable HTTP 503 before a run/agent event was created. No replacement forecast. |
| Squad collaboration | Tests cover joining/concurrent capacity, private membership, fresh Yes/No quotes, swaps, deadline/lock, votes/comments, shared article atomicity, chat SSE replay, final resolution, track records, payout conservation, and escrow freeze. |
| XRPL Testnet spike | Four three-member payout cases and explicit expired escrow refund validated. **50 actual transaction records**, including inner atomic Payments; recipient balances checked. [Public report](../xrpl/reports/2026-10-11-testnet-spike.json). |
| Real app wallet API | Isolated test database created a Testnet wallet with **100 SPC**, verified on-chain balances, and returned the same address on repeated read. [Public report](../xrpl/reports/app-wallet-verification.json). |
| XRPL server safeguards | **19 focused Python tests** cover journaling before effects, wallet/escrow concurrency, uncertain retries, network gating, complete frozen membership, fresh open/final Gemini results, expiry/refund, atomic inner-payment validation, and idempotency. |

The application now has Group betting, Spare, and News tabs, plus a React Flow swarm workspace. Source inspection, event-state tests, and production compilation passed. Browser access to the local preview was previously denied, so rendered layout, clicking through flows, and two-window live visualization have **not** been verified in a browser. No screenshot is presented as evidence. iPhone Shortcuts and PWA device installation remain untested.

Context.dev and Gemini sandbox credentials were supplied and configured in the ignored local `.env`; live reading retrieval, shared-cache reuse, and read-only Gemini authentication passed. Credentials and the private Gemini account name are excluded from source control and deliverables. No Anthropic or Plaid credentials were supplied. Actual Claude forecasts on two markets, Plaid ingestion/webhook delivery, and authenticated Gemini order/combo creation/fill remain unverified. Missing credentials remain visible errors, not substitute content. Build/run setup is in [README](../README.md), and [DEMO](../DEMO.md) lists manual checks.

The actual XRPL transaction checks use only Testnet/Devnet custom SPC tokens. Persistent app wallets need a stable `XRPL_WALLET_KEY`. The full app path from a real finalized Gemini squad through its UI to an XRPL payout has not yet been exercised; the reusable executor's four payout cases and wallet API are verified independently. Recovery after an unknown submission or a partial escrow release near its deadline requires manual reconciliation. Mainnet, RLUSD, multisign, automatic refunds, automated trading, and an authenticated combined Gemini order are not claimed.

Phase D was approved and is implemented: cached forecast chips, The Swarm leaderboard, profiles on shared resolved markets, and durable leg-chat sharing. Twelve additional controlled tests pass, including the real worker completion hook, concurrent retries, cached sharing without credentials, and access isolation. [Run instructions and self-check](SWARM_CONNECTIONS.md). Credentialed Phase D data and browser checks remain pending; no fixture content is served by the app. The separate Digger reading/share/related-market request is implemented.

Reproduce checks from the project root:

```sh
.venv/bin/python -m pytest -q -c backend/pytest.ini backend/tests
.venv/bin/python -m pip check
bash -n run.sh
npm --prefix frontend run build
node --test frontend/src/swarmState.test.js frontend/src/swarmConnections.test.js
npm --prefix swarm run build
npm --prefix swarm test
npm --prefix xrpl run check
npm --prefix xrpl test
```

The XRPL spike submits real test-network transactions. The Gemini combo spike can place a sandbox order when credentials and explicit contract IDs are supplied. Read their documentation before rerunning; never treat submission alone as confirmation.
