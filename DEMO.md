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

If Plaid is still processing, use **Sync purchases** shortly afterward. Repeating **Run demo** creates another batch; syncing reuses transaction IDs and does not duplicate an already ingested purchase. With missing keys, show the actionable error and continue with manual entry. The credentialed Plaid path has not been verified with supplied keys.

## Optional Gemini sandbox order

Follow the [sandbox setup in README.md](README.md#gemini-sandbox-keys). Use your own Gemini sandbox account/key pair, accept the latest Predictions terms yourself, set `TRADING_MODE=sandbox`, and restart. The badge changes to **Sandbox funds** and choices use sandbox quotes.

Add a purchase, choose an affordable outcome, then press **Place sandbox order**. A `filled` response with verified full quantity creates a sandbox position. A cancelled no-fill order keeps the change in rollover. An `unknown` or `open` result remains reserved; use **Verify order status** in Your pot, and inspect the sandbox account if no exchange order ID is available. Do not retry an uncertain order as a new purchase. No production order route exists in this MVP. Credentialed sandbox execution is not claimed as tested.

## Optional reading material

With `CONTEXT_DEV_API_KEY` configured server-side, use the market card’s **Research this market** panel to request Context.dev source links and excerpts. Explain that these are reading materials, not forecasts or additional ranking inputs. Without a key or when the provider fails, the app shows the configuration/provider message. Credentialed retrieval has not been tested in this delivery. See the [Context.dev Search API](https://docs.context.dev/api-reference/web-scraping/search).

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

The Gemini spike attempts a one-contract sandbox order when keys exist; it is an action, not just a health check. Read its `status` and `filledQuantity`; “submitted” is not “filled.” Without keys, private Gemini and Plaid probes report missing configuration. Backend fixtures test local behavior without proving live provider access. A network failure or zero current affordable markets is a valid result to show rather than hiding it with sample data.

For a phone demo, serve the built app on port 8000 and follow [SHORTCUT_SETUP.md](SHORTCUT_SETUP.md). Use a trusted temporary tunnel because this local MVP has no login. Keep one browser origin/profile throughout the demonstration. A new origin or cleared browser storage creates a fresh profile; previous data remains in the local database.
