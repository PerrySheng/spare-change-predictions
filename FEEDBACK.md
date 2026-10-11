# XRPL developer feedback

This feedback describes what this build actually used. It does not claim that an unavailable integration was tested.

## Documentation

The [fungible-token escrow tutorial](https://xrpl.org/docs/tutorials/payments/send-fungible-token-escrows) gave a useful end-to-end path from issuer settings to real escrow transactions. Calling out `asfAllowTrustLineLocking` avoided a token-permission failure. The [single-account Batch tutorial](https://xrpl.org/docs/tutorials/best-practices/transaction-sending/send-a-single-account-batch-transaction) also explains an essential detail: the outer Batch can succeed without all its inner transactions succeeding. We consequently verify each inner transaction hash and token balance change.

The [known-amendments page](https://xrpl.org/resources/known-amendments) records that the original `Batch` was replaced by `BatchV1_1` after a bug. This matters for capability probes. A small current example showing how to query validated amendment status would reduce the chance that a developer checks only the old name, assumes a feature is unavailable, or copies stale network assumptions.

The feature brief called `CancelAfter` an automatic refund safety mechanism. The real API requires an explicit `EscrowCancel` after the deadline. A prominent plain-language sentence about that distinction in every escrow example would help newcomers. Similarly, examples should consistently explain that deadline checks use validated ledger time, not only the computer's clock.

## xrpl.js

We installed xrpl.js 5.3.0, used its published transaction types and enum flags, and ran TypeScript checks. Transaction autofill, signing, validated submission, faucet funding, and inner transaction hashing provide a compact implementation without hand-written transaction serialization. Our secrets enter through stdin and remain AES-GCM encrypted in outputs, so the sample is safe to run without printing faucet seeds into logs.

The public server accepts the documented `ledger_entry` amendments selector, but the published SDK request type did not expose that selector in this version. We used a narrowly scoped structural cast and inspected the real validated response. Adding this selector and its response type would make amendment-aware integrations easier to type-check.

## Ripple MCP server and skill

No callable Ripple or XRPL MCP tools were available in this Codex session, and no Ripple SKILL.md was available to read. We used the official web documentation and xrpl.js directly. This is an availability limitation, not a claim that the MCP server or skill is defective; neither was tested.

## Testability and operational behavior

The runnable spike saves only public addresses, real transaction hashes, explorer links, and verified balance changes. It checks both Testnet and Devnet at runtime. Testnet faucet or server failures stop the run without a mock fallback. Test reports should be consulted for the actual latest outcome; no fixed network availability claim is embedded in the application.

An official sample for an idempotent server operation journal would be valuable. Transport errors after broadcast are uncertain, and retrying with a fresh sequence can duplicate financial operations. It would also help to provide an example that separately persists escrow conditions and encrypted fulfillments before broadcasting.
