# Demo walkthrough

Start with the production build served by FastAPI at [localhost:8000](http://localhost:8000), using the setup in [README.md](README.md). Keep `TRADING_MODE=paper`. No private credentials are included; the manual path demonstrates the app while Gemini supplies real public market data when reachable.

## Three-minute manual demo

1. **Make a profile.** Enter a name, choose interests such as Sports and Crypto, and keep the `$5` weekly cap. Point out the visible **Paper mode** badge.
2. **Add a purchase.** Enter merchant `Starbucks`, amount `$4.63`, and Food & drink. The receipt shows `37¢`, calculated from the purchase rather than a sample round-up.
3. **Explain the choices.** Open **How it works** to show the integer-cent calculation and market scoring factors. Market prices, close times, and rules come from Gemini; up to three distinct events must fit the available change, whole-contract quantity, and estimated fee. The default selection is **Keep it in savings**.
4. **Save the first round-up.** Press **Save my change**. Open **Your pot**: savings should be `$0.37`, and the comparison matches saving that allocated change. Pending round-ups do not count as allocated savings.
5. **Try a paper pick.** Add `Ticketmaster`, `$18.21`, Entertainment: `79¢`. Each suggested contract shows **Yes** and **No** with Gemini's buy quote and an independent contract count and fee. Choose an affordable side and press **Choose paper position · YES/NO**; the confirmation names your choice. A side that needs more money or has no quote cannot be selected. Your pot records that side's paper position and keeps any unspent cents in rollover. If no choice is affordable or the feed fails, show the honest empty/error state and save instead.
6. **Show control.** In preferences, pause market picks or set the cap to `$0`; savings remains available. Activity shows each purchase and its allocation. A `$12.00` purchase produces zero change and is marked **Already a whole dollar**.

Suggested narration: “Every purchase leaves a small decision. Save it, or use test bookkeeping to explore a market you care about. The app shows how it chose the market and includes fees before you confirm.”

Changing interests can change the ranking when matching affordable events exist in the current feed. Do not promise a specific event, result, price, win, or ranking change: this demo uses current provider data. A successful paper pick is not an exchange order. Open market value uses the current sell quote before an exit fee; a missing quote displays **Unavailable**. The app does not implement selling.

## Optional Plaid demo

Set `PLAID_CLIENT_ID` and a Plaid **sandbox** `PLAID_SECRET` in the root `.env`; keep `PLAID_ENV=sandbox` and restart the backend. Obtain credentials from the [Plaid Dashboard](https://dashboard.plaid.com), using the [sandbox guide](https://plaid.com/docs/sandbox/).

Press **Run demo** once. It creates these test transactions through Plaid's sandbox API and reads their actual sync results:

| Merchant | Purchase | Round-up |
| --- | ---: | ---: |
| Starbucks | $4.63 | 37¢ |
| Ticketmaster | $18.21 | 79¢ |
| Shell | $32.56 | 44¢ |
| Total | $55.40 | $1.60 |

If Plaid is still processing, use **Sync purchases** shortly afterward. Repeating **Run demo** creates another batch; syncing reuses transaction IDs and does not duplicate an already ingested purchase. With missing keys, show the actionable error and continue with manual entry. The supplied credentials passed sandbox authentication, sync, and an isolated import of 174 real sandbox purchases with verified round-ups. The three named custom purchases were not separately matched during the bounded check; show the rows that actually arrive and avoid promising a fixed feed or total. [Live check](docs/PLAID_LIVE_CHECK.json).

## Optional Gemini sandbox order

Follow the [sandbox setup in README.md](README.md#gemini-sandbox-keys). Use your own Gemini sandbox account/key pair, accept the latest Predictions terms yourself, set `TRADING_MODE=sandbox`, and restart. The badge changes to **Sandbox funds** and choices use sandbox quotes.

Add a purchase, choose an affordable outcome, then press **Place sandbox order**. A `filled` response with verified full quantity creates a sandbox position. A cancelled no-fill order keeps the change in rollover. An `unknown` or `open` result remains reserved; use **Verify order status** in Your pot, and inspect the sandbox account if no exchange order ID is available. Do not retry an uncertain order as a new purchase. No production order route exists in this MVP. Credentialed sandbox execution is not claimed as tested.

## News and shared reading

With `CONTEXT_DEV_API_KEY` configured server-side, open **News** or a market's **Read in News** link. Select a live market and press **Find reading materials**. Only short summaries and original-source links appear. Open an article's related markets, select Yes/No using an existing round-up, or add your own squad leg. **Share to squad** explicitly posts the link/summary to a selected group's chat, optionally with a leg reaction. Missing keys produce a configuration message. Recent News Scout evidence is reused from the shared cache.

The local server now has Context.dev configured. Its live reading API returned five source links for a real Gemini market, and repeat retrieval used the shared cache. [Public API check](docs/CONTEXT_LIVE_CHECK.json). Clicking through the reading UI still requires a browser check.

## Group betting

1. Open **Group betting**, create a squad, set a future lock time, and copy its invite code. A three-member squad supports the test-token escrow design.
2. Have two friends use separate browser profiles and join with the code. Each chooses their own live Yes/No leg. Change one leg before lock to show a real swap event.
3. React with **Agree** or **Disagree** and an optional comment. Open Chat to see persisted picks, swaps, votes, and shared articles. Two open profiles receive new chat events over SSE.
4. Lock the full slip. Changes and reactions now fail. Use **Refresh results** when Gemini publishes actual outcomes. Track records and category edge use those results, with unresolved picks excluded.
5. Optionally configure XRPL following [XRPL.md](docs/XRPL.md). Open **Orders & settlement**, create/fund each custom-SPC test wallet, and have each member explicitly lock collateral. After all real market outcomes are final, the creator can settle. Open actual transaction explorer links. Do not claim the proposed combined Gemini slip has been placed; that integration is gated.

The reproducible XRPL spike already validated all four three-member payout cases and an expired escrow refund on Testnet. Those are labeled test inputs in the spike, not invented Gemini results in the app. Read [the public ledger evidence](xrpl/reports/2026-10-11-testnet-spike.json).

## Live swarm research

Configure `ANTHROPIC_API_KEY`, build `swarm/`, and restart first. The credentialed path has not been exercised in this delivery.

1. Open a live market from Spare, News, or a squad leg, then choose **Swarm research**. Start a run. Show the real market at the center of the graph and four independent agents around it.
2. Tap News Scout. Show actual search queries, source links, public evidence notes, and its submitted Yes estimate. A quiet panel means the provider hasn't sent those events; no progress is manufactured.
3. Watch Round 2 arrive from the real stream. Revised nodes show the change in percentage points; open the agent panel to read its brief explanation.
4. Show the final research estimate versus the actual recorded Gemini side quote. Explain that the median is computed in code and a price gap does not guarantee a profitable trade.
5. Use **Replay saved run** and **Next event** to step through persisted events. Open the same `/swarm/{runId}` route in a second window of the same profile to verify both receive the same event IDs.

6. Return to Spare or News and show the cached probability chip. Its quote is labeled **at forecast time**. Open it to replay the saved research without another model call.
7. On a squad leg, press **Ask the Swarm · share to chat**, then show the completed summary in **Chat**. Open it from another member’s profile; only squad members can access the shared result.
8. After Gemini genuinely resolves a researched, locked pick, press **Check Gemini results**. Show **The Swarm** under **Track records**, then your **You vs the Swarm** card. An unresolved or unmatched market shows unavailable scores; never invent a settlement to finish the demo.

No automated bot trades are enabled. Phase D’s credentialed flow and browser interaction checks remain pending.

## Verify before presenting

From the project root, run:

```sh
cd backend
../.venv/bin/python -m pytest -q
cd ../frontend
npm run build
cd ..
.venv/bin/python spikes/gemini_spike.py
.venv/bin/python spikes/plaid_spike.py
```

The Gemini spike attempts a one-contract sandbox order when keys exist; it is an action, not just a health check. Read its `status` and `filledQuantity`; “submitted” is not “filled.” Without keys, private Gemini and Plaid probes report missing configuration. Supplied Gemini sandbox credentials passed read-only authentication; supplied Plaid credentials passed Item exchange and actual transaction ingestion. Backend fixtures test local behavior without proving live provider access. A network failure or zero current affordable markets is a valid result to show rather than hiding it with sample data.

For a phone demo, serve the built app on port 8000 and follow [SHORTCUT_SETUP.md](SHORTCUT_SETUP.md). Use a trusted temporary tunnel because this local MVP has no login. Keep one browser origin/profile throughout the demonstration. A new origin or cleared browser storage creates a fresh profile; previous data remains in the local database.

## Railway friend test and Swarm

Open https://spare-production.up.railway.app in separate browser profiles or on friends’ devices. A valid open squad invite can open the access gate and prefill Group betting’s join form. Everyone creates their own profile, joins the same squad, and chooses a different market; another member’s market is disabled and server-side races return 409. Chat and votes are shared over persisted SSE events.

Open a real market’s Swarm chip. Google Gemini analyzes Context.dev reading materials, then the agents debate. Free-tier calls are paced, so allow a couple of minutes. Select News Scout to show the actual Context.dev source links and short public evidence notes. After completion, choose Use as my squad leg, select an open squad and your Yes/No side, and confirm. Swarm never becomes a funded member.

For deployment configuration and verification limits, see docs/RAILWAY_DEPLOYMENT.md and docs/VERIFICATION.md.
