# Spare — two-minute demo script

Read the script below. Aim for about 100 seconds of speech and 20 seconds of screen actions. Start with a completed real Swarm run and a funded Squad Slip ready to open; free-tier research takes longer than the video limit.

Screen sequence: purchase change → accumulated pot → savings or market allocation → shared Squad Slip → confirmed SPC escrow link → News sources → saved Swarm result.

“Hi, I’m Perry, and this is Spare: use the change from everyday purchases to save or invest in prediction markets, and explore them with friends.

Spend $4.63, and Spare calculates 37 cents of change. Every purchase adds more, with no weekly cap. Plaid Sandbox supplies purchase data. Save the change, use it for a pick, or hold it in your pot for a bigger bet later.

Gemini’s Prediction Markets API supplies real events, Yes and No prices, and final results. Search any market, choose a side and amount, and preview potential earnings. This demo uses paper funds.

Squad Slips bring friends onto one shared, combo-style slip. Share an invite code; each friend adds a different Gemini market as their leg. Chat, compare picks, and avoid duplicate or opposing bets on the same event.

Here’s the twist: if your leg cashes, you owe nothing in the squad’s cost-sharing settlement. Members with losing legs split the winning members’ shares.

Everyone first locks SPC test-token collateral into XRP Ledger escrow, with confirmed ledger receipts. Connecting purchase change directly to SPC is planned, so one change wallet can fund both personal picks and squad legs.

Context.dev supplies short reading summaries and source links. Swarm, our research bee, uses Google Gemini AI and that evidence: four agents estimate independently, debate, and combine their forecasts. Research can inform your leg; Swarm contributes no money. This is a saved real run.

Railway hosts Spare so friends can use it together.”

## Explain the squad rule if someone asks

For a three-person squad with a 15 SPC proposed stake, each person's base share is 5 SPC, and each locks 10 SPC of collateral. If one person's leg loses and the other two win, the losing member covers both winners' 5 SPC shares. The loser receives 0 SPC back; each winner receives 15 SPC: their 10 SPC collateral plus 5 SPC. If everyone wins or everyone loses, each gets their 10 SPC collateral back. These are the app's cost-sharing rules, separate from any Gemini exchange payout.

## Keep these details accurate during the demo

- Plaid is Sandbox; personal bets are paper. SPC has no real monetary value.
- The intended product uses one change wallet: 37 cents becomes 0.37 SPC, available to hold, spend on a personal pick, or lock into squad escrow. **That connection is planned.** The current demo accumulates change in the app and funds Testnet SPC wallets separately; it does not withdraw real bank money or convert round-ups into SPC yet.
- For a bigger pick later, choose **Hold in pot for a future market pick**, then **Hold my change**. Dedicated **Keep it in savings** stays separate from the current market budget.
- Say **XRPL**, meaning **XRP Ledger**. Escrow locks SPC collateral on the ledger until it is released or canceled; it is not just an ordinary wallet transfer.
- A winning leg owes nothing in the group cost-sharing calculation, but its owner still deposits collateral first. If everyone wins or everyone loses, collateral is returned without a cost-sharing charge. Voided legs count as not lost.
- Google AI has free-tier limits; a complete Swarm run can take a couple of minutes.
- Gemini powers market data and published results. The shared combo-style slip is recorded in Spare; the UI still says **Not placed** for a combined Gemini exchange order. Show confirmed ledger status before calling SPC funding successful.
- Forecasts can be wrong. A saved Swarm run is real research that previously completed, not a new live run.
- The complete finalized-market-to-payout app flow still needs end-to-end live verification. The escrow executor’s payout cases were verified separately on Testnet.
- XRPL is the open-source XRP Ledger, associated with Ripple’s ecosystem; do not imply Ripple operates this app or sponsors it.

Provider references: [Gemini Predictions](https://developer.gemini.com/predictions), [Context.dev](https://docs.context.dev), [Google AI](https://ai.google.dev/gemini-api/docs/pricing), [Plaid Sandbox](https://plaid.com/docs/sandbox/), [XRPL escrow](https://xrpl.org/docs/concepts/payment-types/escrow), [Railway](https://docs.railway.com).
