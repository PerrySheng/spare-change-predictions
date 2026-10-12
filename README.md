# Spare — make more of your everyday change

**Build up purchase change, research a market, and create a bet slip with friends.**

[Try the live app](https://spare-production.up.railway.app/) · [Two-minute demo script](DEMO_SCRIPT.md) · [Developer setup](docs/DEVELOPER_GUIDE.md)

Spare brings personal picks, shared Squad Slips, news, AI research, and results into one app. You choose where your change goes and can see what happened to your picks afterward.

**Demo:** personal bets use paper funds; squad escrow uses SPC tokens on XRP Ledger Testnet. SPC has no real monetary value, and bank money is not withdrawn. Connecting purchase change directly to SPC is planned.

## Judges: start here

| Feature | What makes it interesting | Where to try it |
| --- | --- | --- |
| **Create a slip together** | Each friend contributes a different Gemini market, with shared discussion and a cost-sharing rule tied to whose leg wins. | Group betting → create or join a squad. |
| **Swarm, the AI research bee** | Four agents research different angles independently, challenge each other, and produce an inspectable forecast. | Open a market → Swarm research. |
| **Funded XRPL escrow** | Collateral is locked before results, reducing reliance on promises to pay after a loss. | Squad → The slip → XRPL test-token escrow. |
| **Chat and accuracy tracking** | Discuss picks, share evidence, then compare the resolved results of friends and Swarm. | Squad → Chat or Track records. |
| **One customer hub** | Purchase change, personal positions, squad activity, and research are accessible through one profile and app. | Spare, Group betting, and News. |

## Create a bet slip together

A **leg** is one person's chosen market and Yes/No side. A **Squad Slip** collects everyone's legs into one shared, combo-style slip.

Spare's twist is that friends build the slip together while keeping ownership of their own picks. Each member brings a different event, discusses it with the group, and can use research to explain their choice. The settlement rule connects responsibility to each person's result.

1. Create a squad, choose its size and proposed stake, and share the invite code.
2. Friends join the same live app from their own browser profiles and each add one leg from a different Gemini event.
3. The first pick reserves its event, blocking duplicate or opposing picks from other members.
4. For funded squads of **3–6 friends**, confirming a pick requests its SPC escrow. Once funded, that pick freezes.
5. The creator can request settlement after every leg has a final Gemini result and every member's collateral is confirmed.

Gemini's Prediction Markets API supplies the real markets, prices, and published results. The shared slip is recorded in Spare; the combined Gemini exchange order is still shown as **Not placed**.

### If your leg cashes, you owe nothing

**Winning legs owe nothing in the squad's cost-sharing calculation.** Members whose legs lose split the winning members' shares. Everyone deposits collateral up front.

Example: three friends choose a 15 SPC stake, with a 5 SPC base share each. Each locks 10 SPC. If one leg loses and two win, the loser covers the winners' two 5 SPC shares. The loser receives 0 SPC back; each winner receives 15 SPC. If everyone wins or everyone loses, each gets their 10 SPC back. These are the app's cost-sharing rules, separate from an exchange payout.

### Talk about picks, then track who was right

Each squad has three tabs side by side:

| Tab | What friends can do |
| --- | --- |
| **The slip** | See everyone's leg, entry price, funding state, and eventual win/loss/void result. React with agree/disagree and comments before a leg freezes. |
| **Chat** | Discuss the bets in a shared live conversation. Post article summaries and links, and share Swarm research attached to a leg. |
| **Track records** | Compare wins, losses, hit rate, and edge scores. Open a friend's profile for category results, streaks, disagreement accuracy, and a chart that updates with each resolved pick. |

Accuracy comes from Gemini's published results. **Hit rate** means the percentage of resolved picks that won. **Edge** also considers the price when the pick was made: a hit scores 1, a miss scores 0, then the entry price is subtracted. Pending and voided picks do not improve those scores.

**The Swarm appears on the same leaderboard**, using the same edge formula. Matching-market comparisons let friends check their results against eligible research shared into that squad. Small samples can be misleading.

## Meet Swarm: four research agents, one market

**Swarm is our AI research bee.** It helps a customer inspect a market from several angles before choosing a side.

| Agent | Its job |
| --- | --- |
| **News Scout** | Find recent reporting and developments relevant to the event. |
| **Base Rate Analyst** | Look for how often similar events have happened before. |
| **Market Reader** | Examine the real Gemini snapshot and market rules, identifying missing data. |
| **Skeptic** | Make the strongest evidence-based case against the leading view. |

First, each agent makes its own estimate without seeing the others' answers. Next, they review one another's estimates and explain any revisions. Application code calculates the **median** of the four revised probabilities: the average of the middle two. A final Synthesizer call explains that fixed result.

The customer sees **Swarm's probability versus the market price**, supporting reasons, disagreements, and source links. The live visualization follows real agent events; completed runs can be replayed.

### Why this is more useful than one generic AI answer

| Swarm's design | Benefit for the customer |
| --- | --- |
| Different research roles | News, historical patterns, market data, and counterarguments each get a dedicated review. |
| Independent first estimates | Agents commit to an initial view before discussion, making changes and convergence visible. |
| An explicit Skeptic and debate | The process requires challenges to the leading view rather than only supporting arguments. |
| Aggregation in code | A median limits one extreme estimate's influence; the summary model cannot overwrite the number. |
| Sources and disagreement shown | Customers can inspect the evidence and uncertainty behind the result. |
| Saved forecasts and later scoring | Accuracy can be measured against resolved events over time. |

The advantage is **a structured, visible cross-checking process**. The agents currently use the same underlying Google Gemini model in separate calls; they can still share biases. Spare has not yet demonstrated higher forecasting accuracy than a single-model baseline. Research takes more calls and time than one answer, and forecasts can be wrong.

The approach draws on published work on [multi-agent debate](https://arxiv.org/abs/2305.14325) and [retrieval and forecast aggregation](https://arxiv.org/abs/2402.18563). Those studies motivate the design; they do not establish Spare's accuracy.

A researched pick can become **your own squad leg**. You choose the side and supply the collateral. Swarm contributes no tokens.

## XRPL escrow: a shared squad treasury

**Spare acts as the group's shared treasurer, with XRP Ledger escrow holding the collateral.** Friends commit tokens before the result, so the group does not have to start collecting payment from a losing member afterward.

Once escrow is confirmed, its tokens are locked and cannot be spent freely while the escrow conditions apply. A member cannot simply pull out that collateral because they dislike the outcome. Expired escrow can be returned through the cancellation process. This behavior comes from [XRPL's escrow rules](https://xrpl.org/docs/concepts/payment-types/escrow).

Spare reads the Gemini results, calculates who owes what, and coordinates release and payout. The ledger supplies confirmed transaction receipts. The escrow executor can send the intended payouts together in one **all-or-nothing transaction**.

This is a group treasury and escrow function. The demo uses custom **SPC tokens on XRPL Testnet** and app-managed wallets. XRPL does not independently determine which bet won; the app supplies that result. A locked balance is proof of collateral, not proof that final settlement has completed. The full finalized-market-to-payout app flow still needs live end-to-end verification.

## Your change, picks, and research in one place

The customer has one app and profile for:

- **Spare:** purchase history, available change, dedicated savings, personal positions, and results.
- **Group betting:** their leg, shared slips, escrow receipts, chat, and track records.
- **News / The Digger:** short reading summaries and source links across sports, politics, weather, crypto, entertainment, and the economy.
- **Swarm research:** forecasts connected to the selected market and shareable into squad chat.

Related markets connect reading to personal picks or squad legs. Completed Swarm research can inform the same selections. Customers can follow the path from purchase change to research, a pick, and its result inside Spare.

### Hold your change for a bigger bet later

A **$4.63** purchase creates **37¢** of round-up change. Every purchase can add more, with no weekly cap. A whole-dollar purchase adds zero.

| Your goal | Choose in Spare → Your change |
| --- | --- |
| Build a balance for a larger pick later | **Hold in pot for a future market pick**, then **Hold my change**. |
| Keep dedicated savings | **Keep it in savings**, then **Save my change**. |
| Explore a market now | Choose a market, Yes or No, and an amount; review the quote. |

**You do not have to bet after every purchase.** For example, 37¢ + 79¢ + 44¢ builds $1.60. A later purchase can use its new round-up plus that held balance for a larger pick. Unspent cents carry forward. Dedicated savings stays separate from the current market budget.

The planned wallet connection makes **37¢ equal 0.37 SPC**, with that same change balance available to hold, use for a personal pick, or lock into squad escrow. Today, purchase change and paper positions work in the app; SPC wallets receive separate test-token funding. **The shared change-to-SPC balance is planned, not implemented.**

## What powers Spare?

| Service | What it contributes |
| --- | --- |
| **Plaid Sandbox** | Test purchase data for calculating round-ups. |
| **Gemini Prediction Markets API** | Real market questions, Yes/No prices, and published outcomes. |
| **Context.dev** | Reading summaries and source links, cached and shared between News and Swarm. |
| **Google Gemini AI** | Swarm's research agents and debate; this is a separate service from Gemini's exchange. |
| **XRP Ledger** | Test-token balances, collateral escrow, and inspectable transaction receipts. |
| **Railway** | A shared deployment and persistent database for friends to collaborate. |

The app uses React and Vite on the frontend, and Python, FastAPI, and SQLite on the backend. Click effects adapt React Bits ClickSpark with its license retained.

## Evidence and next steps

The release passed **245 backend tests, 27 frontend tests, 9 Swarm tests, and 8 XRPL tests**. Real checks covered [three-profile squad collaboration and SPC escrow](docs/RAILWAY_MULTIPLAYER_CHECK.json), [Google/Context.dev research and a funded Swarm leg](docs/RAILWAY_SWARM_CHECK.json), and [two different live forecasts](docs/SWARM_GOOGLE_LIVE_CHECK.json).

Planned or awaiting verification: the shared purchase-change-to-SPC wallet, combined Gemini exchange orders, the complete resolved-squad payout flow, and device/browser checks. See the [verification record](docs/VERIFICATION.md).

## For developers

Start with the [setup and configuration guide](docs/DEVELOPER_GUIDE.md). It includes local installation, optional API keys, accounting rules, and test commands. Keep credentials in your private `.env`.

More detail: [Demo walkthrough](DEMO.md) · [Phone Shortcut setup](SHORTCUT_SETUP.md) · [Railway deployment](docs/RAILWAY_DEPLOYMENT.md) · [XRPL implementation](docs/XRPL.md) · [Swarm implementation](docs/SWARM_BACKEND.md).
