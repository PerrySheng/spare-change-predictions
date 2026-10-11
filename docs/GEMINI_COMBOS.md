# Gemini combined orders: verified contract, pending private test

Checked on October 11, 2026. A combo is a separate Gemini instrument whose YES outcome requires every selected leg to meet its selected side. Buying individual contracts is not a combined order. The app must not price a combo by multiplying individual market prices.

## What is documented

The [official REST reference](https://developer.gemini.com/prediction-markets-spec/combos) describes creating or retrieving a canonical combo using `POST /v1/prediction-markets/combos`. It takes 2–6 distinct underlying legs and uses the authenticated account. Reordering the same legs returns the same canonical combo. It requires `PredictionsNewOrder` access and an unrestricted account. Production availability is explicitly limited in this reference; the adapter uses `https://api.sandbox.gemini.com` exclusively.

The request sent through Gemini's signed private authentication is:

```json
{
  "legs": [
    {"contractId": "101", "requiredOutcome": "Yes"},
    {"contractId": "202", "requiredOutcome": "No"}
  ]
}
```

Those numbers are documentation examples, not usable market IDs. `contractId` must be a verified decimal string; `requiredOutcome` is capitalized. The response contains `combo` and `alreadyExisted`. The combo supplies `id`, `canonicalLegKey`, `legCount`, `legs`, `instrumentRegistered`, and, when registered, `instrumentSymbol`. Creation may return HTTP 201 or HTTP 200. The adapter validates that the returned leg set matches the requested one. See the [official schemas](https://developer.gemini.com/prediction-markets-spec/~schemas).

After registration, one ordinary [prediction-market order](https://developer.gemini.com/prediction-markets-spec/trading) uses that returned combo symbol:

```json
{
  "symbol": "<instrumentSymbol returned by Gemini>",
  "orderType": "limit",
  "side": "buy",
  "outcome": "yes",
  "quantity": "2",
  "price": "0.45",
  "timeInForce": "fill-or-kill",
  "makerOrCancel": false
}
```

The explicit limit is chosen for the combo itself; `0.45` above is only a request example. No single-market prices enter the adapter. `outcome: yes` means all the already-selected leg sides must succeed. An HTTP acceptance is not proof of a fill. Check `orderId`, `status`, `filledQuantity`, `remainingQuantity`, and `avgExecutionPrice`; reconcile via `/v1/prediction-markets/orders/active` or `/v1/prediction-markets/orders/history` without repeating placement.

The official SDK corroborates this workflow. At [SDK commit 6dd34bee](https://github.com/gemini/developer-platform/tree/6dd34bee51d263079615da84c2d8b15fbea3df83), TypeScript exposes `predictions.createCombo`, `predictions.listCombos`, `predictions.getComboByInstrumentSymbol`, and `predictions.placeOrder`. The Go SDK exposes `PredictionsService.CreateCombo`. The implementation is in [generated TypeScript REST operations](https://github.com/gemini/developer-platform/blob/6dd34bee51d263079615da84c2d8b15fbea3df83/packages/sdk-typescript/src/generated/operations.ts) and [Go combo service](https://github.com/gemini/developer-platform/blob/6dd34bee51d263079615da84c2d8b15fbea3df83/packages/sdk-go/services/predictions_combos.go).

## RFQ does not supply a documented taker create/accept API

The reviewed [RFQ overview](https://developer.gemini.com/prediction-markets/combos-rfq/overview) and [quote methods](https://developer.gemini.com/prediction-markets/combos-rfq/quote-methods) cover maker quoting. The SDK exposes `rfq.submitQuote`, `rfq.withdrawQuote`, and `rfq.confirmQuote`, plus public discovery and authenticated delivery streams. No documented requester method for creating an RFQ or accepting its winning quote was found in that API or SDK surface. The app therefore does not invent `rfq.create`, `rfq.accept`, private REST equivalents, or a batch-of-singles fallback.

## What actually ran

- `GET https://api.sandbox.gemini.com/v1/prediction-markets/combos?limit=2`: HTTP 200 at `2026-10-11T20:34:25Z`. Pagination reported 103 combo records. The returned sample contained real combo contract IDs `106144` and `106128`, with 2 and 6 legs respectively. This proves public discovery only.
- The default private spike exited with code 2 and a missing-key message before sending any HTTP request. `GEMINI_API_KEY` and `GEMINI_API_SECRET` were absent. Canonical creation, terms/account eligibility, actual combined order placement, and a combined fill remain unverified.
- Controlled response tests pass for signing/host restrictions, exact legs and selected sides, one combined order, no automatic retries, incomplete responses, ambiguous execution, and safe reconciliation. These tests do not represent private venue execution.

An additional integration gap is explicit: the event feed currently returns IDs such as `203737-295784`, while the combo request requires a decimal `contractId`. The reviewed event schema does not document how to derive that underlying ID from the composite event ID. The adapter rejects a composite ID or market symbol instead of splitting it. A verified metadata source or clarification from Gemini is required before connecting arbitrary Squad Slip selections to canonical creation.

## Run the spike

From the repository root:

```sh
# Public discovery, no credentials or mutation:
.venv/bin/python spikes/gemini_combo_spike.py --public-only

# Account/terms preflight only, after configuring sandbox keys in .env:
.venv/bin/python spikes/gemini_combo_spike.py

# Canonical creation only, using two REAL underlying contract IDs:
.venv/bin/python spikes/gemini_combo_spike.py \
  --leg "$LEG_ONE_ID:yes" --leg "$LEG_TWO_ID:no" --create

# Explicitly place ONE sandbox test order at a chosen combo limit:
.venv/bin/python spikes/gemini_combo_spike.py \
  --leg "$LEG_ONE_ID:yes" --leg "$LEG_TWO_ID:no" \
  --place-test-order --quantity 1 --limit-price "$COMBO_LIMIT_PRICE" \
  --journal work/gemini-combo-attempt.json

# Read-only recovery for a known provider order ID:
.venv/bin/python spikes/gemini_combo_spike.py \
  --symbol "$COMBO_SYMBOL" --order-id "$GEMINI_ORDER_ID" \
  --quantity 1 --limit-price "$COMBO_LIMIT_PRICE"

.venv/bin/python -m pytest -q -c backend/pytest.ini backend/tests/test_combos.py
```

The journal is exclusively created before placement. Reusing it cannot place a second order. If a timeout leaves the attempt unknown and no order ID was returned, inspect the sandbox account manually. Do not retry that attempt. The spike does not accept account terms for the user.

## Recommended application endpoint contract

Keep combined placement unavailable until the authenticated private spike and contract-ID mapping are verified. The local squad/chat/track-record functions can operate independently.

Once those checks pass, a server-side prepare operation can accept a squad/slip ID, resolve its frozen legs to verified underlying IDs, call `SandboxCombos.create`, and persist the returned canonical symbol. An order operation should accept an immutable local attempt ID, explicit whole-contract quantity, and an authorized combo limit price. Reserve the approved budget and persist `submitting` **before** sending exactly one order. Repeated requests for that attempt must return its journal entry instead of calling the provider again.

Persist the canonical leg set, returned combo ID/symbol, quantity, limit price, order ID if received, response, and timestamps. A definite `ProviderRejected` can release the local reservation; a transport failure or ambiguous response must keep it reserved as `unknown`. A read-only reconcile endpoint calls `SandboxCombos.status`. Only a verified full fill produces a group position; a verified zero-fill cancellation releases the reservation. The HTTP adapter cannot supply persistence or exactly-once execution by itself. Settlement and any XRPL collateral transfers are separate from Gemini's combined order.
