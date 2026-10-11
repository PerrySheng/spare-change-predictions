# XRPL test-network settlement

The XRPL module uses only the public **Testnet** and **Devnet**. It refuses a mainnet name or arbitrary server URL and confirms the remote server's network ID before doing anything. `SPC` is a custom issued test token with no monetary value. It is **not RLUSD**, and there is no claim that a test token is redeemable for dollars. No official obtainable RLUSD test faucet/issuer was verified for this build; the brief's permitted custom-token option is used explicitly.

We combine issued-token trust lines, token escrow, SHA-256 crypto-conditions, and an all-or-nothing payout Batch. A group's collateral stays in an escrow until the app reveals the matching fulfillment. That secret is held by the app, so these are **custodial test wallets**, not a decentralized oracle or production custody system. Multi-sign approval is not implemented.

## Network capability checks

The module reads the Amendments ledger entry from a **validated ledger**. It checks `TokenEscrow` and the current replacement `BatchV1_1`. The original `Batch` amendment was disabled after a bug; checking only that original amendment would give the wrong answer for current network capability. Both amendments are required before the spike proceeds, and no sequential-payment fallback is implemented. The public report includes the ledger index/hash and check timestamp, so the check is reproducible rather than a permanent hardcoded availability claim.

See [known amendments](https://xrpl.org/resources/known-amendments), [TokenEscrow / XLS-85](https://xls.xrpl.org/xls/XLS-0085-token-escrow.html), and [Batch / XLS-56](https://xls.xrpl.org/xls/XLS-0056-batch.html).

## Run the real spike

From the project root, with Node 22 or later:

```sh
cd xrpl
npm ci
npm test
npm run check
npm run spike -- testnet
```

Use `devnet` in place of `testnet` to run on the other allowed network. The spike first probes **both** networks, then creates faucet-funded accounts for an issuer, the settlement account, and three members. It enables issuer Default Ripple and Allow Trust Line Locking, creates trust lines, and gives each member 100 SPC test tokens. It demonstrates an expired escrow refund through an explicit `EscrowCancel`, then runs complete one-loser, two-loser, all-win, and all-lose settlements. Each settlement creates and finishes three conditional token escrows and sends all positive payouts in one atomic Batch.

Every submitted transaction hash is recorded. The outer Batch result alone is insufficient: the module calculates each inner transaction hash, looks it up in the validated ledger, and checks recipient token-balance changes. A report is written to `xrpl/reports/spike-latest.json` with public addresses, hashes, explorer links, balances, and actual success or failure. It does not contain seeds or fulfillments. Faucet/network failures stop the run; it never fabricates hashes or success data.

The spike uses a disposable encryption key in memory when none is configured. Wallet seeds are never printed or saved. Its throwaway test accounts are not reused by the application. For persistent app wallets, configure the encryption key explicitly before calling the server CLI.

## CancelAfter is a refund deadline, not an automatic refund

`CancelAfter` makes an escrow eligible for cancellation after that time. A real `EscrowCancel` transaction still has to be submitted and validated. The ledger does **not** automatically move funds at the deadline. The cancellation path checks validated ledger close time before submission. The spike waits for ledger time to pass the deadline; it does not assume a local timer proves cancellation is allowed.

See [EscrowCreate](https://xrpl.org/docs/references/protocol/transactions/types/escrowcreate), [EscrowFinish](https://xrpl.org/docs/references/protocol/transactions/types/escrowfinish), and [EscrowCancel](https://xrpl.org/docs/references/protocol/transactions/types/escrowcancel).

## Collateral and payouts

Let `S` be the total stake in cents, `n` the number of members, and `L` the number of losing legs. Each member locks `S - S/n`. Voided legs count as not lost. When nobody loses or everyone loses, each member receives their full collateral back. Otherwise, every non-losing member receives an extra `S/n`, funded by the losers. Losers split that transfer equally. If the split has a fractional cent, extra cents are assigned deterministically in member order. The sum of payouts always equals the sum of collateral. Stake cents must divide evenly by the member count, and squads contain 2–8 members because a Batch permits at most eight inner transactions.

For `S = 1500` cents and three members, each locks 1000 cents:

| Result | Payouts, in member order | Total |
| --- | --- | --- |
| First member loses | 0, 1500, 1500 | 3000 |
| First two members lose | 750, 750, 1500 | 3000 |
| All win | 1000, 1000, 1000 | 3000 |
| All lose | 1000, 1000, 1000 | 3000 |

Zero payouts are omitted from the Batch. At least two positive payouts are required by the protocol. A two-member group where exactly one loses has only one positive payout, so that specific settlement must be rejected before locking collateral until a separately approved protocol design exists. The module does not silently substitute an individual Payment.

## Server CLI contract

The Python server may call `xrpl/node_modules/.bin/tsx xrpl/cli.ts` with the working directory at the project root. Send **one JSON object through stdin** and read one JSON object from stdout. Do not pass private data in command-line arguments. Successful output has `ok: true`; errors have `ok: false`, a sanitized `error`, and any known `transactions`. The CLI exits with status 1 on error. `npm run cli` adds npm headers to stdout, so server code should invoke `tsx` directly.

Every input has `operation` and `network: "testnet"` or `"devnet"`. A probe needs no key. Wallet operations require `XRPL_WALLET_KEY` in the subprocess environment, containing a canonical base64 encoding of 32 random bytes. Keep this stable, private, and backed up alongside the database. Encryption uses AES-256-GCM with 12-byte random IV, AAD `spare-xrpl-v1`, and a packed base64 envelope `IV || ciphertext || 16-byte authentication tag`. Both seeds and escrow fulfillments use this envelope.

| Operation | Additional stdin fields | Result fields |
| --- | --- | --- |
| `probe` | None | `status`: network ID, validated ledger/time, amendments |
| `setup` | None | `issuer` and `settlement`, each `{address, encrypted_seed}`; `currency` |
| `wallet-create` | Optional `issuer: {address, encrypted_seed}` | `wallet: {address, encrypted_seed}`; creates a trust line and funds 100 SPC when issuer is supplied |
| `escrow-create` | `encrypted_seed`, `destination`, `issuer_address`, `amount_cents`, `cancel_after` | `owner`, `offer_sequence`, `condition`, `encrypted_fulfillment`, `cancel_after`, `hash`, `explorer_url` |
| `escrow-finish` | Signer's `encrypted_seed`, `owner`, `offer_sequence`, `condition`, `encrypted_fulfillment` | `hash`, `explorer_url` |
| `escrow-cancel` | Signer's `encrypted_seed`, `owner`, `offer_sequence` | `hash`, `explorer_url` |
| `batch-payout` | Settlement signer's `encrypted_seed`, `issuer_address`, `payouts: [{address, cents}]` | `hash`, `explorer_url`, validated `inner_transactions`, before/after `balances` |

`cancel_after` is a timestamp in **Ripple epoch seconds**, not Unix seconds: subtract 946684800 from a Unix timestamp. It must be at least 20 seconds after the last validated ledger's close time. The server should place it comfortably after the latest expected market resolution. The CLI uses `SPC` consistently and cannot change token currency based on caller input.

All successful operations also include `status` and `transactions: [{label, type, hash, explorer_url, result, ledger_index}]`. A hash is saved in the in-memory result **before broadcast**. A transport failure leaves a submitted-unconfirmed record, which must be reconciled by that exact hash.

## Integration and recovery requirements

The application server must persist an operation journal before invoking the CLI, keep one operation per wallet serialized, and block fresh retries after an uncertain submission. It must store each escrow's owner, creation sequence, condition, encrypted fulfillment, cancellation deadline, and transaction journal. The CLI is an executor, not an idempotency database. A process crash can happen between submitting a transaction and returning its result. In that case, inspect validated account history and match the intended operation before proceeding; never create a fresh escrow or payout as an automatic retry. If a crash loses the fulfillment, the escrow can only be safely recovered through cancellation after its deadline.

The app should reconcile all escrow finishes, confirm the settlement account has the collateral, then submit the payout Batch once. It must never report "settled" merely because the outer Batch validated. It must confirm every inner Payment and expected balances. The app's Gemini event-resolution data controls when it decides to reveal fulfillments; XRPL does not independently verify prediction outcomes. Faucet-funded test balances do not establish any real-money payment flow.

Reference implementation: [official token-escrow tutorial](https://xrpl.org/docs/tutorials/payments/send-fungible-token-escrows), [official single-account Batch tutorial](https://xrpl.org/docs/tutorials/best-practices/transaction-sending/send-a-single-account-batch-transaction), and [xrpl.js source](https://github.com/XRPLF/xrpl.js).

## Verified run on 2026-10-11

The real Testnet spike completed all four settlements, with 50 validated transaction records including the inner Payments. Both Testnet and Devnet probes reported TokenEscrow and BatchV1_1 enabled; the original Batch was disabled. The archived public evidence is `xrpl/reports/2026-10-11-testnet-spike.json`.

| Case | Validated all-or-nothing payout Batch |
| --- | --- |
| One loser | [604DE147…](https://testnet.xrpl.org/transactions/604DE14719A9E534184BDAE9B037E76396D47BB7C0581CE7EAF94019B7B43714) |
| Two losers | [3E6DFF68…](https://testnet.xrpl.org/transactions/3E6DFF688B7A731FC150387E8100EEF4F3AFA28A394FE72753C98E769A4A915D) |
| All win | [71DB5C50…](https://testnet.xrpl.org/transactions/71DB5C507D46757F0A4E1CE157F7A5664190E501147A623971A5E23A36770711) |
| All lose | [A63E2735…](https://testnet.xrpl.org/transactions/A63E2735537C4B44A7E9830DC937B2ED39FA8074EB4136A38B2543A91588F1EF) |

The explicit [expired-escrow cancellation](https://testnet.xrpl.org/transactions/D7104C4E5B09DBDFDF3738EFFC2B715899FCFE28A7202AEA7B917C8A0B34F766) validated, and its ledger metadata shows the member's trust-line balance returning from 90 to 100 SPC. No Devnet transaction run was necessary because all required primitives worked on Testnet; Devnet was probed, not claimed as fully exercised.
