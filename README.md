# Spare — make more of your everyday change

**Save your purchase change, build it up for a bigger pick, or explore prediction markets with friends.**

[Try the live app](https://spare-production.up.railway.app/) · [Read the two-minute demo script](DEMO_SCRIPT.md) · [Watch the build checks](https://github.com/PerrySheng/spare-change-predictions/actions)

Spare rounds purchases up to the next dollar and lets you choose what happens to the difference. It combines a change pot, Gemini prediction markets, shared Squad Slips, news reading, and Swarm, our AI research bee.

The public demo uses **paper betting and SPC tokens on XRP Ledger Testnet**. SPC has no real monetary value, and bank money is not withdrawn.

## How your change works

Buy something for **$4.63**, and its round-up is **37¢**. Every purchase can add more change; there is no weekly cap. A whole-dollar purchase adds zero.

You have three choices:

| What you want | What to choose |
| --- | --- |
| Build up change for a bigger bet later | **Hold in pot for a future market pick**, then **Hold my change**. |
| Put the change aside as dedicated savings | **Keep it in savings**, then **Save my change**. |
| Use available change for a market now | Choose a market, Yes or No, and an amount. Review the quote before confirming. |

**You do not have to bet after every purchase.** Hold your change in the pot and let it build up. For example, round-ups of 37¢, 79¢, and 44¢ add up to $1.60. A later purchase can use its new round-up plus that held balance for a larger pick. Unspent cents carry forward.

Find these choices under **Spare → Your change**. **Your pot** shows your savings, held change, and positions. Dedicated savings stays separate from the amount available for market picks, so use **Hold in pot** when you want to bet later.

### One change wallet — planned connection

The intended product has **one wallet**, with SPC representing accumulated purchase change: **37¢ becomes 0.37 SPC**. You could keep it there for later, use it for a personal pick, or lock part of it into squad escrow. These are uses of the same change balance.

**Connecting purchase change to the SPC wallet is planned.** Today, change accumulation and paper picks work in the app; the demo's SPC wallets receive separate test-token funding. The demo does not yet convert round-ups into SPC or spend one shared balance across both paths.

## Find a market and choose a side

Gemini's Prediction Markets API supplies the real events, prices, and published results.

- Browse suggestions based on your interests, purchase categories, and previous picks, or search by title and category.
- Choose **Yes** or **No**. Events with multiple outcomes show a separate row for each outcome.
- Pick an amount and see the potential payout update immediately.

Each winning contract pays $1. For example, 73¢ at a 40¢ Yes price previews **Win $1.83 (+$1.10)** before fees. That preview uses fractional math; the confirmed quote buys whole contracts that fit your balance and shows the estimated fee. A forecast or preview does not guarantee a win.

## How Squad Slips work

A **leg** is one friend's selected market and side. A Squad Slip collects everyone's legs into one shared, combo-style slip.

1. Open **Group betting**, create a squad, and choose the group size and proposed stake.
2. Send friends the invite code. Everyone uses the same live app URL and their own browser profile.
3. Each friend adds one leg from a different Gemini event. The first pick reserves that event, blocking duplicate or opposing picks from other members.
4. Chat, react to picks, share reading, or use Swarm research to help choose your own leg.
5. For a funded squad of **3–6 friends**, confirming a pick requests its SPC collateral transfer into XRPL escrow. A funded pick freezes; its transfer is confirmed only after the ledger validates it.
6. After every leg has a final Gemini result and every member's collateral is confirmed, the creator can request settlement.

### If your leg cashes, you owe nothing

In the squad's cost-sharing calculation, **winning legs owe nothing**. Members whose legs lose split the winning members' shares. Everyone still deposits collateral up front.

For example: three friends choose a 15 SPC stake, making each base share 5 SPC. Each locks 10 SPC as collateral. If one leg loses and two win, the loser covers both winners' 5 SPC shares. The loser receives 0 SPC back; each winner receives 15 SPC. If everyone wins or everyone loses, each gets their 10 SPC collateral back.

Gemini powers the markets and results. The shared slip is recorded in Spare; a combined Gemini exchange order is still shown as **Not placed**. The cost-sharing calculation is separate from an exchange payout.

### Where the squad tokens go

The **XRP Ledger (XRPL)** locks SPC collateral in escrow while the squad waits for results. Transaction links let you inspect the confirmed token movement. The app reads Gemini's results and calculates the payouts; XRPL records the escrow and transfers.

These are app-managed Testnet wallets. The escrow code can pay recipients together in one all-or-nothing transaction. The complete finalized-market-to-payout app flow still needs live end-to-end verification.

## Read first, then ask Swarm

**News / The Digger** offers short summaries and original source links across sports, politics, weather, crypto, entertainment, and the economy. Context.dev supplies the reading materials. Related markets let you go from an article to a personal pick or squad leg.

**Swarm** is the research bee. Four AI agents study news, historical patterns, market data, and counterarguments independently. They compare their answers, revise, and produce a combined probability estimate with sources. The visualization follows real agent events, and completed runs can be replayed.

You can add a researched pick as **your own** squad leg. You choose the side and supply the collateral; Swarm contributes no tokens. Its forecasts are research and can be wrong.

## What powers Spare?

| Service | What it does and why it helps |
| --- | --- |
| **Plaid Sandbox** | Supplies test purchase data, so change can be calculated from transactions. |
| **Gemini Prediction Markets API** | Provides real market questions, Yes/No prices, and published outcomes. |
| **Context.dev** | Finds reading materials and source links; News and Swarm share cached results to avoid repeat searches. |
| **Google Gemini AI** | Powers Swarm's independent research agents and debate. This is a different service from Gemini's prediction-market exchange. |
| **XRP Ledger** | Records test-token balances, locks squad collateral in escrow, and provides transaction receipts. |
| **Railway** | Hosts the shared app and persistent database so friends can collaborate on the same slip. |

The frontend uses React and Vite; the backend uses Python, FastAPI, and SQLite. Click effects adapt React Bits ClickSpark with its license retained.

## Run it on your computer

You need **Python 3.11+** and **Node.js 22.12+**. From the project folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
cp .env.example .env
npm --prefix frontend ci
npm --prefix swarm ci
npm --prefix swarm run build
npm --prefix xrpl ci
./run.sh
```

Open [localhost:8000](http://localhost:8000). `run.sh` builds the frontend and starts the backend. Manual purchase entry and paper picks use public market data; optional integrations need your own keys in `.env`.

| Feature | Keys to configure |
| --- | --- |
| Plaid test purchases | `PLAID_CLIENT_ID` and `PLAID_SECRET` from Sandbox. |
| News reading | `CONTEXT_DEV_API_KEY`. |
| Google-powered Swarm | `GOOGLE_AI_API_KEY`, `CONTEXT_DEV_API_KEY`, and `SWARM_PROVIDER=gemini`. |
| SPC test wallets and escrow | A stable `XRPL_WALLET_KEY` encryption key; use `XRPL_NETWORK=testnet`. |
| Optional Gemini sandbox orders | `GEMINI_API_KEY` and `GEMINI_API_SECRET`; master keys also need `GEMINI_ACCOUNT`. |

Restart after changing `.env`. Keep keys private. Full configuration, fee rules, sandbox setup, and troubleshooting are in the [developer guide](docs/DEVELOPER_GUIDE.md).

## Tested work and next steps

The release passed **244 backend tests, 26 frontend tests, 9 Swarm tests, and 8 XRPL tests**. Real checks also covered [three-profile squad collaboration and SPC escrow](docs/RAILWAY_MULTIPLAYER_CHECK.json), [Google/Context.dev Swarm research and a funded research leg](docs/RAILWAY_SWARM_CHECK.json), and [two different live forecasts](docs/SWARM_GOOGLE_LIVE_CHECK.json).

Planned or still awaiting verification: the purchase-change-to-SPC wallet connection, combined Gemini exchange orders, the complete resolved-squad payout flow, and device/browser checks. See the [verification record](docs/VERIFICATION.md) for details.

Useful guides: [Demo walkthrough](DEMO.md) · [Phone Shortcut setup](SHORTCUT_SETUP.md) · [Railway deployment](docs/RAILWAY_DEPLOYMENT.md) · [XRPL details](docs/XRPL.md) · [Swarm setup](docs/SWARM_BACKEND.md).
