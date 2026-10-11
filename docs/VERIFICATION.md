# Verification record

Checked on October 11, 2026. Paper mode is enabled by default. Controlled provider fixtures are confined to tests; the application never returns sample forecasts, articles, markets, or transaction hashes.

| Check | Result |
| --- | --- |
| Python backend suite | **179 passed**. One existing Starlette TestClient/httpx deprecation warning. |
| Frontend production build | Passed with Vite 7.3.7. Swarm loads in a separate chunk; initial JS 312 kB before gzip. |
| Frontend event reducer | **2 Node tests passed**: real-event state transitions, revision history, replay order/deduplication, safe source links. |
| Claude TypeScript worker | Build and **5 tests passed**: median, search-tool permissions, JSON/source validation, actual stream query parsing, public text versus hidden thinking. |
| XRPL TypeScript executor | TypeScript checks and **8 tests passed**: networks, crypto-condition, payout conservation, issued-token cents, atomic Batch flags, encryption. |
| Python dependencies / launch | `pip check`, `bash -n run.sh`, and Git whitespace checks passed. |
| Local server | `/health`, `/`, current built assets, manifest, service worker, and `/swarm/example` frontend route returned HTTP 200. OpenAPI confirms squads/news/swarm/quote/XRPL routes. |
| Live Gemini | Actual public production and sandbox market data retrieved; prior fee-aware Yes/No paper allocations verified. |
| Digger personalization | Two new isolated profiles made actual paper allocations against live Gemini quotes. Sports history put sports first; crypto history put crypto first. [Raw check](NEWS_SELF_CHECK.json). |
| Shared research sources | Controlled tests prove News reuses persisted News Scout metadata without requiring another Context.dev call, and users/history/related instruments are scoped and computed. |
| Claude missing key | Live-market run requests returned actionable HTTP 503 before a run/agent event was created. No replacement forecast. |
| Squad collaboration | Tests cover joining/concurrent capacity, private membership, fresh Yes/No quotes, swaps, deadline/lock, votes/comments, shared article atomicity, chat SSE replay, final resolution, track records, payout conservation, and escrow freeze. |
| XRPL Testnet spike | Four three-member payout cases and explicit expired escrow refund validated. **50 actual transaction records**, including inner atomic Payments; recipient balances checked. [Public report](../xrpl/reports/2026-10-11-testnet-spike.json). |
| Real app wallet API | Isolated test database created a Testnet wallet with **100 SPC**, verified on-chain balances, and returned the same address on repeated read. [Public report](../xrpl/reports/app-wallet-verification.json). |
| XRPL server safeguards | **19 focused Python tests** cover journaling before effects, wallet/escrow concurrency, uncertain retries, network gating, complete frozen membership, fresh open/final Gemini results, expiry/refund, atomic inner-payment validation, and idempotency. |

The application now has Group betting, Spare, and News tabs, plus a React Flow swarm workspace. Source inspection, event-state tests, and production compilation passed. Browser access to the local preview was previously denied, so rendered layout, clicking through flows, and two-window live visualization have **not** been verified in a browser. No screenshot is presented as evidence. iPhone Shortcuts and PWA device installation remain untested.

No Anthropic, Context.dev, Plaid, or private Gemini credentials were supplied. Therefore actual Claude forecasts on two markets, real Context.dev reading, Plaid ingestion/webhook delivery, and authenticated Gemini order/combo creation/fill remain unverified. Missing credentials remain visible errors, not substitute content. Build/run setup is in [README](../README.md), and [DEMO](../DEMO.md) lists manual checks.

The actual XRPL transaction checks use only Testnet/Devnet custom SPC tokens. Persistent app wallets need a stable `XRPL_WALLET_KEY`. The full app path from a real finalized Gemini squad through its UI to an XRPL payout has not yet been exercised; the reusable executor's four payout cases and wallet API are verified independently. Recovery after an unknown submission or a partial escrow release near its deadline requires manual reconciliation. Mainnet, RLUSD, multisign, automatic refunds, automated trading, and an authenticated combined Gemini order are not claimed.

The next swarm integration phase (cached suggestion chips, The Swarm leaderboard/player comparison, and posting a forecast into squad chat) remains pending the user's phase checkpoint. The separate Digger reading/share/related-market request is implemented.

Reproduce checks from the project root:

```sh
.venv/bin/python -m pytest -q -c backend/pytest.ini backend/tests
.venv/bin/python -m pip check
bash -n run.sh
npm --prefix frontend run build
node --test frontend/src/swarmState.test.js
npm --prefix swarm run build
npm --prefix swarm test
npm --prefix xrpl run check
npm --prefix xrpl test
```

The XRPL spike submits real test-network transactions. The Gemini combo spike can place a sandbox order when credentials and explicit contract IDs are supplied. Read their documentation before rerunning; never treat submission alone as confirmation.
