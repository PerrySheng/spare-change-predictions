# Spare Change Predictions

A mobile-first React PWA that turns a USD purchase into a choice: keep the round-up in savings or use it for an affordable Gemini prediction-market position. The default is **paper mode**: savings and positions are local bookkeeping, and no money moves. The optional order path uses **Gemini sandbox test funds only**. Production money trading is disabled.

The frontend uses React, Vite, Tailwind CSS, and Lucide icons. The backend uses FastAPI, SQLAlchemy, and SQLite. Market choices come from Gemini's public Predictions API; unavailable data produces a visible error or empty state, never invented markets. Plaid Sandbox can supply test purchases through real API calls when credentials are configured. Manual purchase entry works without private provider keys.

## Run locally

Use Python 3.11+ and Node.js 20.19+ within the 20.x line, or 22.12+ (the installed Vite version's supported Node ranges). Run these commands from the project root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
cp .env.example .env
cd frontend
npm ci
npm run build
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

- Onboard with a name, interests, and a weekly market cap. A $0 cap allows savings only; preferences can pause market picks. The cap includes contract cost and estimated fees and resets Monday at midnight in `America/Los_Angeles`.
- Add a USD purchase manually, through a `/roundup` Shortcut link, or through Plaid Sandbox. `$4.63` becomes `37¢`; a whole-dollar purchase creates no round-up. Amounts are stored as integer cents.
- Choose savings or hold the round-up for a future market pick, or explore up to three contracts from distinct live events. Each market card lets you choose **Yes or No** using Gemini's actual buy quote for that side, with its own contract count and fee. A side that exceeds the available budget or has no executable quote is visible but unavailable to select. Savings is selected first, and each allocation requires a user choice.
- See the calculation, scoring factors, and market rules under **How it works**. Deterministic ranking combines interests, spending, prior topic picks, affordability, time to close, and reported event volume. Wins and losses do not affect ranking.
- Track saved change, rollover available for future picks, pending round-ups, positions, wins/losses, and a comparison with saving every allocated round-up.
- In the optional Context.dev reading panel, load source links and snippets for a market. Reading material is informational and does not change ranking or predict the outcome. Credentialed retrieval has not been verified in this delivery.

Market discovery is cached for 15 seconds. Before allocating a position, the backend fetches the event again, rejects closed markets, rejects a price increase above the displayed price, and never exceeds the displayed contract count or total cost. It buys whole contracts that fit the available round-up plus rollover, the weekly cap, and the contract's quantity grid. Unspent change stays in rollover; saved change is separate.

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
| `GEMINI_NONCE_MODE=time` | Match the key's nonce setting; `incremental` is also supported. |
| `GEMINI_TAKER_RATE=0.07` | Taker fee estimate. |
| `PLAID_CLIENT_ID`, `PLAID_SECRET` | Optional client ID and **sandbox** secret for test purchases. |
| `PLAID_ENV=sandbox` | The only supported Plaid environment. |
| `PLAID_WEBHOOK_URL` | Optional public HTTPS URL ending in `/webhooks/plaid`, configured before the first demo connection. |
| `CONTEXT_DEV_API_KEY` | Optional server-side key for the market reading panel. |
| `DATABASE_URL=sqlite:///./spare_change.db` | SQLite database, relative to the backend working directory. |

### Gemini sandbox keys

Register or sign in yourself at the [Gemini sandbox exchange](https://exchange.sandbox.gemini.com), following Gemini's [sandbox guide](https://developer.gemini.com/get-started/sandbox). In that sandbox account, open Settings → API and create an account API key with the required trading/order-status permissions. Match its nonce mode to `GEMINI_NONCE_MODE`. Store the key and secret in `.env`. See [Gemini API key authentication](https://developer.gemini.com/authentication/api-key).

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

### Optional Context.dev reading

Add `CONTEXT_DEV_API_KEY` to the root `.env` and restart to enable reading materials. The adapter searches with only the public Gemini event title and contract label; purchase history, interests, balances, and positions are not sent. It returns at most five source links with short snippets and a fetch timestamp, and caches public queries for ten minutes. Empty results and partial results are shown as such. The panel does not generate an answer or alter market scores. Without a key, it shows an actionable configuration message. Credentialed retrieval remains untested. See the [Context.dev Search API](https://docs.context.dev/api-reference/web-scraping/search).

## Checks and provider spikes

From the project root:

```sh
cd backend
../.venv/bin/python -m pytest -q
cd ..
.venv/bin/python spikes/gemini_spike.py
.venv/bin/python spikes/plaid_spike.py
```

Backend tests cover money parsing, round-ups, fee-aware quantity sizing, scoring, duplicate IDs, isolation by user ID, single allocation, caps/pausing, price changes, provider failures, and settlement credited once. Tests use controlled provider fixtures; passing them does not verify a credentialed provider integration.

The Gemini spike first reads public production markets, then reads sandbox markets and attempts **one sandbox contract order** if keys are present. Run it only when you intend that test. It prints `sandbox_order: not_verified` and an actionable reason if the private path fails; submission alone is not proof of a fill. The Plaid spike creates one sandbox test purchase and polls for its actual transaction. Missing keys yield a clear error; a delayed transaction is reported as processing rather than substituted. Credentialed Gemini, Plaid, and Context.dev calls remain unverified until you configure keys and inspect successful responses.

## Phone demo and limitations

After the production build is served on port 8000, follow [SHORTCUT_SETUP.md](SHORTCUT_SETUP.md) for an HTTPS phone tunnel and Apple Pay automation. [DEMO.md](DEMO.md) gives a short walkthrough that starts without credentials.

This is a local hackathon MVP without login. A browser stores its profile ID in `localStorage`; that ID is not authentication. Use a tunnel only with trusted demo participants, and stop it afterward. Changing tunnel domains creates a different browser origin/profile. Keep provider keys server-side and use test data. Plaid Item tokens are stored in the local SQLite database.

The PWA manifest and service worker support a home-screen app shell in a secure browser context. The service worker caches the shell/assets, never financial/provider responses; allocations and fresh data still need the backend and network. Device installation, Apple Pay trigger fields, credentialed exchange orders, and credentialed reading retrieval require separate testing on your device/accounts.

Project layout: `frontend/` holds the React PWA; `backend/app/` holds API, accounting, scoring, and provider adapters; `backend/tests/` holds deterministic tests; `spikes/` holds standalone provider probes.
