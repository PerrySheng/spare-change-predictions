# Apple Pay Shortcut setup

The app accepts a purchase link in this form:

```text
https://YOUR-DEMO-HOST/roundup?amount=4.63&merchant=Starbucks&id=PURCHASE-UUID
```

Opening the link records one purchase for the profile remembered by that browser, calculates its round-up, and opens the choice screen. The user still chooses savings or a market. This setup does not transfer bank funds or place an order automatically.

## Put the app on your phone

1. Build the frontend and start FastAPI on port 8000 using [README.md](README.md#run-locally). Verify [localhost:8000](http://localhost:8000) works on the computer first.
2. If you already have ngrok installed/configured, start an HTTPS tunnel in another terminal:

   ```sh
   ngrok http 8000
   ```

   Otherwise, follow the official [ngrok localhost guide](https://ngrok.com/docs/start) to configure it yourself, then run the command. Point the tunnel at **8000**, where the production frontend and API share one origin.
3. Open the resulting HTTPS URL in Safari on the iPhone. Complete onboarding there before using the Shortcut. `localhost` on the phone refers to the phone, not your computer.
4. Optionally use Safari's Share menu to add the PWA to the Home Screen. Test the link in the browser that stores your profile; do not assume a Home Screen window and Safari share the same storage on every OS version.

This MVP has no login. Share the tunnel only with trusted demo participants, keep it temporary, and stop it after the demo. A changed tunnel domain is a new browser origin and may require onboarding again. Credentials remain in the computer's root `.env`, never in the URL or Shortcut.

## Build and test a manual Shortcut first

Create a Shortcut named **Spare Change** with this sequence. Action labels can vary by iOS version.

1. **Ask for Input** for the purchase amount. Keep a USD amount such as `4.63`, using a dot as the decimal separator and no more than two decimal places. Do not pass a different currency as USD.
2. **Ask for Input** for the merchant name, for example `Starbucks`.
3. Generate a UUID for this purchase and store it in a variable named `Purchase ID`. If a UUID action is unavailable on your OS, use an explicit unique ID for the manual test. A date/time alone can collide; a stable transaction identifier is preferable if available.
4. URL-encode the amount, merchant, and purchase ID **individually** using the URL Encode action or its equivalent. Do not encode the entire URL: `/`, `?`, `&`, and `=` must remain separators.
5. Use a **Text** or **URL** action to assemble:

   ```text
   https://YOUR-DEMO-HOST/roundup?amount=[Encoded Amount]&merchant=[Encoded Merchant]&id=[Encoded Purchase ID]
   ```

   Insert the real variables where the bracketed labels appear; do not send the bracketed labels literally.
6. **Open URLs** with that URL. Keep the resulting browser origin/profile consistent.

Test a literal link before wiring the variables:

```text
https://YOUR-DEMO-HOST/roundup?amount=4.63&merchant=Coffee%20%26%20Co.&id=shortcut-test-001
```

Expected behavior: the receipt says `Coffee & Co.`, the purchase is `$4.63`, the round-up is `37¢`, and the source is **Shortcut**. The browser replaces the link with `/` after successful persistence. Reopening the same link with the same ID creates no second purchase for that profile. Use `shortcut-test-002` for a different test purchase.

## Connect it to a transaction automation

Apple documents a **Transaction** trigger with a **When I tap** card option in its [Shortcuts transaction trigger guide](https://support.apple.com/guide/shortcuts/transaction-trigger-apd65c67538a/ios). Select the documentation version that matches your phone. The guide does not guarantee which amount, merchant, currency, or stable ID variables every device/card transaction will expose.

1. In Shortcuts, open **Automation**, add a transaction automation, and select the card/trigger options available on your device.
2. Inspect the automation's actual transaction input using a temporary **Show Result** or **Quick Look** action. Verify the amount, merchant, currency, and any identifier fields on your own device. Do not assume a field name from a different iOS version or assume online Apple Pay purchases behave like a card tap.
3. If an actual USD amount and merchant are available, pass those verified fields into the URL-building sequence above. Normalize the amount to a plain dot-decimal USD value. If the fields are absent or ambiguous, retain **Ask for Input** so you can confirm the purchase details instead of sending fabricated values.
4. Use the transaction's stable unique identifier if one is actually supplied. Otherwise generate **one new UUID per automation invocation/purchase** before constructing the URL. Preserve that value for retries of the same purchase; do not regenerate it on each retry. Creating a new UUID for a rerun of the same event can duplicate it.
5. Configure execution/confirmation options available on your OS, then test the trigger with your own device. The repository includes the web endpoint, not an installed iPhone automation or a claim that automatic execution has been tested.

## Duplicate handling and data limits

The backend deduplicates by profile, source (`shortcut`), and purchase `id`. Reusing an ID with a changed amount or merchant produces HTTP 409; correct the details instead of silently turning that ID into another purchase. Every separate Apple Pay purchase needs a different ID. If `id` is omitted, the browser creates one and keeps it in session storage for a reload of that URL, but an explicit ID is required for reliable retries across sessions.

Purchase amounts must be positive USD values with at most two decimals; `$4.63`, `USD 4.63`, and `4.63` are accepted. The URL does not include a spending category, so the purchase is initially uncategorized. Merchant names can still contribute to the deterministic scoring rules. A whole-dollar amount creates zero change. A purchase is recorded first; allocation is a separate user action.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Phone cannot connect | Computer/backend and tunnel are still running; use the HTTPS tunnel URL, not the phone's localhost. |
| App loads but API calls fail | Tunnel points to port 8000; build exists before FastAPI starts; restart backend after the first build. |
| Onboarding appears again | URL origin changed, browser storage was cleared, or you opened a different browser/PWA storage context. |
| Amount is rejected | USD only; dot decimals; no more than two decimal places; no unsupported currency symbol. |
| Merchant is truncated or URL breaks | Encode each query value separately, especially spaces, `&`, `+`, and `#`. |
| Purchase already has different details | Same ID was used with a different amount/merchant. Preserve the original purchase's details; generate a new ID only for a new purchase. |
| No market choices | Cap may be zero/reached, picks paused, no whole contract fits including its fee, or Gemini is unavailable. Savings remains available. |
| Automation has no amount/merchant | Inspect actual input for your OS/card and use manual confirmation if needed. Do not guess missing transaction data. |

Remove the temporary inspection actions after testing because they can display purchase details. Provider keys are never needed on the phone.
