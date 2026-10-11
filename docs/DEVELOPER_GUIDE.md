# Developer guide

A mobile-first React PWA that turns a USD purchase into a choice: keep the round-up in savings or use it for an affordable Gemini prediction-market position. The default is **paper mode**: savings and positions are local bookkeeping, and no money moves. The optional order path uses **Gemini sandbox test funds only**. Production money trading is disabled.

The frontend uses React, Vite, Tailwind CSS, and Lucide icons. The backend uses FastAPI, SQLAlchemy, and SQLite. Market choices come from Gemini's public Predictions API; unavailable data produces a visible error or empty state, never invented markets. Plaid Sandbox can supply test purchases through real API calls when credentials are configured. Manual purchase entry works without private provider keys.

## Wallet connection status

The intended product has one change wallet: 37 cents of purchase change becomes 0.37 SPC, and that balance can be held for later picks or locked into squad escrow. **This connection is planned, not implemented.** The current demo records purchase change in the app and funds its SPC Testnet wallets separately.

## Run locally

Use Python 3.11+ and Node.js 22.12+ for the frontend, AI worker, and XRPL executor. Run these commands from the project root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
cp .env.example .env
cd frontend
npm ci
npm run build
cd ../swarm
npm ci
npm run build
cd ../xrpl
npm ci
cd ../backend
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

After installing dependencies, you can also start the app with `./run.sh` from the project root. It rebuilds the frontend and starts the backend.

Open [the app](http://localhost:8000), [API docs](http://localhost:8000/docs), or [health status](http://localhost:8000/health). FastAPI serves the built frontend and API from the same origin. Build before starting the backend; restart it after the first build so it mounts the assets. The `.env` file belongs at the project root, beside `.env.example`, and is loaded there by the backend and spikes. With the default database URL, starting from `backend` stores data in `backend/spare_change.db`.

For frontend development, keep the backend running and use a second terminal:

```sh
cd frontend
npm run dev
```

Vite proxies `/api` to the backend on port 8000. Use the backend on port 8000 for the built demo and phone tunnel: the production bundle makes API calls to its own origin. `npm run preview` alone does not provide that backend.

## What the app does

- Onboard with a name and interests. Change from every purchase accumulates in your available balance, without a weekly cap. Settings can pause market picks.
- Add a USD purchase manually, through a `/roundup` Shortcut link, or through Plaid Sandbox. `$4.63` becomes `37¢`; a whole-dollar purchase creates no round-up. Amounts are stored as integer cents. Bank amounts with fractional cents are rounded to the nearest cent (half cents round up) before calculating change; manual USD input remains limited to two decimal places.
- Browse tailored events or search the full current catalog by title, category, and outcome. Binary events have Yes/No buttons; multi-outcome events show four rows sorted by chance and a Show more toggle. Both sides use observed venue prices. Live earnings previews follow the selected side and amount. Clearly labeled demo examples include binary and multi-outcome inputs and cannot place orders or start research.
- See the calculation, scoring factors, and market rules under **How it works**. Deterministic ranking combines interests, spending, prior topic picks, affordability, time to close, and reported event volume. Wins and losses do not affect ranking.
- Track saved change, rollover available for future picks, pending round-ups, positions, wins/losses, and a comparison with saving every allocated round-up.
- Switch between **Group betting**, **Spare**, and **News**. Spare keeps Your change, Activity, and Your pot as secondary pages.
- Build a squad slip with 2–6 friends, invite codes, one distinct market and Yes/No leg each, pre-lock swaps, agree/disagree votes, comments, live chat, and real resolved track records. Picks are proposed until a provider transaction is separately confirmed.
- Use **News / The Digger** for Context.dev source links and short summaries. Its topic order reflects interests and actual paper/squad picks, with a sample-weighted positive category edge boost. Read an original article, choose a related live market, add your own squad leg, or explicitly share an article into squad chat.
- Open **Swarm**, the research bee, for four independent AI forecasts, one debate round, a code-computed median, and a mobile React Flow workspace. Google Gemini uses Context.dev reading evidence; Claude remains an optional provider. Only actual calls and persisted events drive activity. Completed research can become your own squad leg on either side: you choose and fund it; Swarm contributes no money.
- With XRPL configured, use encrypted custodial Testnet/Devnet wallets and custom SPC token escrows for squads of 3–6 members. A confirmed settlement pays every recipient in one atomic Batch. SPC has no real monetary value; round-ups and savings stay separate.

Market discovery is cached for 15 seconds. Before allocating a position, the backend fetches the event again, rejects closed markets, rejects a price increase above the displayed price, and never exceeds the displayed contract count or total cost. It buys whole contracts that fit the accumulated purchase change plus rollover and the contract's quantity grid. Unspent change stays in rollover; saved change is separate.

The fee estimate is `ceil(0.07 × contracts × price × (1 − price) × 100)` cents. This implements the published taker formula and rounding; it remains an estimate and can be overridden with `GEMINI_TAKER_RATE`. Check the current [Gemini Predictions fee schedule](https://www.gemini.com/fees/predictions) before changing the estimate.

Open positions are valued using the current Gemini sell quote, before any exit fee; the app does not implement selling. Published outcomes credit $1 per winning contract once, while invalid markets refund contract cost. Missing quotes or unresolved sandbox orders make total value and the savings comparison unavailable instead of presenting a complete value.

## Configuration

No private provider credentials are supplied. Add only credentials you own to the root `.env`, and restart the backend after changes.

| Variable | Purpose |
| --- | --- |
| `TRADING_MODE=paper` | Default: local positions using public Gemini market data. |
| `TRADING_MODE=sandbox` | Enables sandbox order submission and uses sandbox market prices. |
| `GEMINI_MARKET_URL=https://api.gemini.com` | Public discovery host in paper mode; sandbox mode selects the sandbox host. |
| `GEMINI_API_KEY`, `GEMINI_API_SECRET` | Optional Gemini **sandbox** key pair for test orders. Never enter production keys. |
| `GEMINI_ACCOUNT` | Required for master keys: the sandbox account short name returned by `/v1/account/list`. Account keys do not use this default. |
| `GEMINI_NONCE_MODE=time` | Match the key's nonce setting; `incremental` is also supported. |
| `GEMINI_TAKER_RATE=0.07` | Taker fee estimate. |
| `PLAID_CLIENT_ID`, `PLAID_SECRET` | Optional client ID and **sandbox** secret for test purchases. |
| `PLAID_ENV=sandbox` | The only supported Plaid environment. |
| `PLAID_WEBHOOK_URL` | Optional public HTTPS URL ending in `/webhooks/plaid`, configured before the first demo connection. |
| `CONTEXT_DEV_API_KEY` | Server-side key for News and Swarm reading materials and the shared source cache. |
| `SWARM_PROVIDER=gemini` | Google AI with Context.dev evidence; `anthropic` enables the existing Claude worker. |
| `GOOGLE_AI_API_KEY` | Google AI Studio key, separate from the Gemini exchange key. |
| `GOOGLE_AI_MODEL=gemini-3.5-flash-lite` | Free-tier-capable model verified against the supplied key; model access and quota depend on your account. |
| `ANTHROPIC_API_KEY` | Server-side key for real research swarm calls. |
| `ANTHROPIC_MODEL=claude-sonnet-5-5` | Documented model; the worker checks actual account/model capabilities before paid calls. |
| `XRPL_NETWORK=testnet` | Only `testnet` or `devnet`; mainnet is refused. |
| `XRPL_WALLET_KEY` | Stable base64 32-byte encryption key for custodial test-wallet seeds and escrow fulfillments. Back it up with the database. |
| `APP_PUBLIC_DEMO=true` | Opens the production paper/Testnet demo without a shared access code; signed profile protection remains. |
| `DATABASE_URL=sqlite:///./spare_change.db` | SQLite database, relative to the backend working directory. |

### Gemini sandbox keys

Register or sign in yourself at the [Gemini sandbox exchange](https://exchange.sandbox.gemini.com), following Gemini's [sandbox guide](https://developer.gemini.com/get-started/sandbox). In that sandbox account, open Settings → API and create an account API key with the required trading/order-status permissions. Match its nonce mode to `GEMINI_NONCE_MODE`. Store the key and secret in `.env`. A master key also requires `GEMINI_ACCOUNT`, using its actual account short name; the adapter includes it in signed prediction-market requests. Sandbox account-list, balance, and accepted-terms access have passed a read-only credentialed check; no order was placed or filled. [Public check](GEMINI_AUTH_CHECK.json). See [Gemini API key authentication](https://developer.gemini.com/authentication/api-key).

Review and accept the latest Predictions terms in your sandbox account. The app checks acceptance before placing an order; it does not accept terms for you. Set:

```dotenv
TRADING_MODE=sandbox
GEMINI_MARKET_URL=https://api.sandbox.gemini.com
GEMINI_API_KEY=your-sandbox-key
GEMINI_API_SECRET=your-sandbox-secret
```

Sandbox orders are signed requests to `api.sandbox.gemini.com`. The app reserves the quoted cost locally, submits a limit order with `fill-or-kill`, and records a position only after verifying a full fill. A definite rejection or verified no-fill cancellation restores the reservation to rollover. An uncertain result remains reserved; use **Verify order status** in Your pot. If no exchange order ID was returned, inspect the sandbox account manually. The app never retries an uncertain order automatically. See the [order API](https://developer.gemini.com/rest-api/prediction-markets/order-management/place-order) and [Predictions API reference](https://developer.gemini.com/prediction-markets-spec).

### Plaid sandbox purchases

Obtain a client ID and sandbox secret yourself from the [Plaid Dashboard](https://dashboard.plaid.com). See [Plaid Sandbox](https://plaid.com/docs/sandbox/). With those values in `.env`, **Run demo** creates a dynamic sandbox Item via `/sandbox/public_token/create`, exchanges its public token, creates Starbucks `$4.63`, Ticketmaster `$18.21`, and Shell `$32.56` test transactions, then ingests the results of `/transactions/sync`. Each press creates another set of test purchases; use **Sync purchases** to fetch delayed results without creating more.

Only posted, positive USD purchases are ingested. Transaction IDs prevent repeated syncs from duplicating purchases. Changed amounts update unallocated round-ups; an amount changed after allocation is flagged for review. Removed unallocated purchases and modifications that become pending, non-positive, or non-USD are made unavailable for allocation. Without credentials, the demo shows an actionable error and leaves manual entry available. See the [sandbox API](https://plaid.com/docs/api/sandbox/), [Transactions API](https://plaid.com/docs/api/products/transactions/), and [webhook verification reference](https://plaid.com/docs/api/webhooks/webhook-verification/).

### News and Context.dev reading

Add `CONTEXT_DEV_API_KEY` to the root `.env` and restart to enable reading materials. The adapter searches with only the public Gemini event title and contract label; purchase history, interests, balances, and positions are not sent. It returns at most five source links with short snippets and a fetch timestamp, and caches public queries for ten minutes. News and the Swarm also share normalized public sources in SQLite for 30 minutes, so a recent result set can be reused without another search. Empty results and partial results are shown as such. News does not alter round-up suggestion scores or produce a forecast. Source summaries are shown alongside live Gemini contracts matched by topic; topic matching does not establish that an article supports an outcome. Without a key, it shows an actionable configuration message. Credentialed retrieval was verified on October 11, 2026: an actual Gemini market returned five Context.dev source links, and a repeat request reused the shared cache. [Public verification record](CONTEXT_LIVE_CHECK.json). Browser interaction remains unverified. See the [Context.dev Search API](https://docs.context.dev/api-reference/web-scraping/search).


### Research swarm

Install/build `swarm/` as above. For the deployed Google provider, set `SWARM_PROVIDER=gemini`, `GOOGLE_AI_API_KEY`, and `CONTEXT_DEV_API_KEY` in the root `.env`, then restart. The optional Claude provider uses `SWARM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. On a market, choose **Swarm research**, select which quote to compare, then press **Run the research swarm**. The run has a shareable local route `/swarm/{runId}` for the same browser profile. Source links and public evidence notes appear when the actual provider emits them; hidden model reasoning is never exposed.

News Scout researches recent reporting; Base Rate Analyst looks for documented historical reference classes; Market Reader uses only the real Gemini snapshot; Skeptic examines counter-evidence. The first four calls run in parallel without seeing each other's estimates. Each then sees the independent answers and may revise. Application code takes the median of the four revised Yes probabilities (the mean of the middle two). A ninth Synthesizer call explains that fixed result. A No comparison uses `1 − p(Yes)` and Gemini's actual No quote, never a fabricated complementary price.

Runs are limited to two per profile per hour, with a 30-minute completed-run cache. Google mode allows one active run globally and a one-minute cooldown; the optional Claude mode allows two concurrent runs. Search-enabled roles get at most two searches each; debate and synthesis do not search. Fresh cached evidence can omit a new search tool. Actual token/search usage is stored. Every event is saved before being streamed over SSE, and saved runs can be stepped through using **Replay saved run**. Failed or interrupted calls never produce a completed forecast.

Prospective results retain their entry quote. When Gemini resolves a market, the backend computes Brier score `(p(Yes) − actual_yes)^2`, and side edge `hit − side_quote_at_forecast`. Voids are excluded, and only one score is recorded per forecast. Lower Brier is better; a small sample proves little. Cached forecast chips now appear on Spare, News, and squad legs. **Ask the Swarm · share to chat** saves a request to post the completed research once. **Track records** ranks The Swarm using the same edge formula as friends; profiles compare the same resolved markets in this squad using explicitly shared research. Only the earliest eligible research completed before picks locked counts, and missing side quotes stay unavailable. See [Phase D setup and self-check](SWARM_CONNECTIONS.md). No bot trades are enabled.

See [research and primary sources](../RESEARCH.md), [phase plan](SWARM_PLAN.md), and [backend API/setup](SWARM_BACKEND.md). Real Google and Context.dev two-market forecasts passed; see [the recorded runs](SWARM_GOOGLE_LIVE_CHECK.json). Claude calls remain unverified without an Anthropic account. Browser permission was denied earlier; no rendered UI or two-window verification is claimed.

### Squad slips and test-token settlement

Create a squad in **Group betting**, give friends the invite code, and have each friend join from a separate browser profile. Members can change their own leg before locking, react with optional comments, and share reading. The friends table shows actual wins/losses/voids, hit rate, entry-price edge, category records, streaks, and resolved disagree accuracy. **Refresh results** reads Gemini's published outcome; it never chooses a result for the demo.

The Gemini combo adapter supports the documented canonical-combo plus single FOK order flow, but combined placement remains gated: authenticated order creation/fill and a reliable decimal contract-ID mapping have not been verified. Read-only sandbox authentication and accepted terms have passed. The UI says **Not placed**. See [Gemini combo verification](GEMINI_COMBOS.md).

For XRPL, follow [XRPL setup and evidence](XRPL.md). Configure a stable encryption key before creating wallets. When configured, onboarding requests a faucet-funded custodial test wallet in the background; an outage leaves onboarding usable and the wallet panel shows its actual state. Existing profiles can use **Create & fund my test wallet**. Confirming a funded pick immediately requests that member’s SPC escrow. Its leg freezes while pending, and only a validated ledger transaction marks collateral locked. Remaining friends can join and pick different events while the partial slip gathers collateral. A later pick must close within the existing escrow window. The complete squad then freezes; failed or uncertain transfers are visible and do not manufacture funds. Two-member slips can collaborate but cannot use this Batch escrow design. Stake cents must divide evenly by member count.

The creator can settle only after every member's collateral is confirmed and every leg has a fresh final Gemini result. The server reveals escrow fulfillments and submits one all-or-nothing payout Batch, verifying inner payments and balances. The app journals each external action before submission and blocks uncertain retries. Refunds require a real **EscrowCancel** after validated ledger time passes the deadline; `CancelAfter` does not automatically refund. This is a test-token experiment, with app-held keys and app-observed Gemini outcomes; multisign approval is not implemented.

## Checks and provider spikes

From the project root:

```sh
cd backend
../.venv/bin/python -m pytest -q
cd ..
.venv/bin/python spikes/gemini_spike.py
.venv/bin/python spikes/plaid_spike.py
```

Backend tests cover money parsing, round-ups, fee-aware quantity sizing, scoring, duplicate IDs, signed production sessions, isolation by user ID, single allocation, pooled purchase change/pausing, price changes, provider failures, and settlement credited once. Tests use controlled provider fixtures; passing them does not verify a credentialed provider integration.

The Gemini spike first reads public production markets, then reads sandbox markets and attempts **one sandbox contract order** if keys are present. Run it only when you intend that test. It prints `sandbox_order: not_verified` and an actionable reason if the private path fails; submission alone is not proof of a fill. The Plaid spike creates one sandbox test purchase and polls for its actual transaction. Missing keys yield a clear error; a delayed transaction is reported as processing rather than substituted. Gemini order creation/fill remains unverified. Supplied Plaid sandbox credentials passed authentication and an isolated app import of 174 actual sandbox purchases with computed round-ups; the three named custom purchases were not separately matched during the bounded check, and webhook delivery is untested. [Plaid check](PLAID_LIVE_CHECK.json). Read-only Gemini sandbox authentication, Context.dev search, and shared-cache retrieval have also been verified.

## Phone demo and limitations

After the production build is served on port 8000, follow [SHORTCUT_SETUP.md](../SHORTCUT_SETUP.md) for an HTTPS phone tunnel and Apple Pay automation. [DEMO.md](../DEMO.md) gives a short walkthrough that starts without credentials.

For local development, name onboarding stores a profile ID in localStorage. The public Railway demo opens without a shared code, while signed Secure/HttpOnly cookies tie each browser to one profile; knowing another profile ID cannot impersonate them. Recoverable public accounts are not implemented. Private friend access remains available when APP_PUBLIC_DEMO=false. Everyone must use the same Railway URL; localhost has a different database. See [Railway deployment](RAILWAY_DEPLOYMENT.md).

The PWA manifest and service worker support a home-screen app shell in a secure browser context. The service worker caches the shell/assets, never financial/provider responses; allocations and fresh data still need the backend and network. Device installation, Apple Pay trigger fields, credentialed exchange orders, and the reading UI require separate testing on your device/accounts. The reading API has passed a live Context.dev check.

Project layout: `swarm/` holds the official Google GenAI and Claude TypeScript workers; `xrpl/` holds the test-network executor and public ledger evidence; `frontend/` holds the React PWA; `backend/app/` holds API, accounting, scoring, and provider adapters; `backend/tests/` holds deterministic tests; `spikes/` holds standalone provider probes.

## Swarm costs and evidence

Google mode requests up to nine calls: four independent estimates, four revisions after debate, and one public summary. The final YES probability is the median of the four revisions, computed in code. Context.dev provides short search descriptions and source links, shared with News through a 30-minute persisted cache; no full articles are displayed. Market Reader only sees the Gemini snapshot. It cannot invent missing history or volume. Public notes are explicitly generated explanations; private thoughts and signatures are discarded.

The free-tier implementation permits four request starts per 61 seconds, one active run globally, a one-minute cooldown between runs, and two new runs per profile per hour. These controls apply across friends and persist across server restarts through the run records. Google can still return quota or temporary capacity errors. Cached forecasts and shared results do not trigger new model calls. Google Search tools are disabled; Context.dev and Railway costs remain separate. [Google pricing](https://ai.google.dev/gemini-api/docs/pricing).

A winning contract pays $1. The fractional earnings preview uses amount / price and is labeled before fees; actual execution buys whole contracts on the venue grid and shows its own fee-aware total. $0.73 at 40¢ previews Win $1.83 (+$1.10), while the executable contract count can be lower. The click response adapts [React Bits ClickSpark](https://reactbits.dev/animations/click-spark), retaining its license and reduced-motion support.

## Try it and present it

[Live demo](https://spare-production.up.railway.app) · [Public source](https://github.com/PerrySheng/spare-change-predictions) · [Two-minute demo script](../DEMO_SCRIPT.md).

News now includes the complete open-market list instead of the first 40 contracts, recognizes political/climate category aliases, and offers real Context.dev subject reading when no related market is open. [Two genuine Google + Context.dev forecast runs and event logs](SWARM_GOOGLE_LIVE_CHECK.json) are saved as public verification evidence, not runtime fixtures.

Live deployment evidence: [three-profile collaboration and actual SPC escrow](RAILWAY_MULTIPLAYER_CHECK.json), [real cloud Swarm, streamed events, and researched member-funded leg](RAILWAY_SWARM_CHECK.json). CI builds and tests the public source without provider keys.
