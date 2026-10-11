# Claude research swarm — proposed phases

Status: Phase A research delivered and Phase B explicitly approved. Phase B backend is implemented and tested with controlled interfaces. The user then requested a nice swarm UI, so the Phase C workspace is implemented alongside the tabs. Real Claude two-market and two-window checks remain blocked by the missing API key and earlier denied browser permission. Digger Phase I connections are implemented under the separate user request. Phase D was explicitly approved and its cache-chip, leaderboard/profile, and durable squad-chat integrations are implemented with controlled integration tests. Its real-data check remains pending a Claude API key; the optional trading bot remains outside the approved phase.

## Outcome

A person opens a live Gemini market, starts research, watches four agents gather evidence independently, sees their revisions after a debate round, and receives a concise probability comparison. Every displayed state and replay event must come from a real provider call or its persisted result. No invented forecasts, sources, price history, progress, or trading actions.

Use the official Anthropic TypeScript SDK in a small Node worker, coordinated by the existing FastAPI backend. Proposed model: documented `claude-sonnet-5-5`, configurable after account-capability verification. `ANTHROPIC_API_KEY` stays in the server environment. No key is supplied yet, so live self-checks require configuration.

## Phase B: Backend and measurement

Add SQLite tables `swarm_runs`, `swarm_events`, `swarm_estimates`, `market_snapshots`, and `research_sources`. Runs record the market/rules snapshot, requester, model, state, exact quotes at forecast time, usage, timestamps, final probability, summary, and resolution. Events have monotonically increasing IDs and public evidence notes; estimates retain both rounds, confidence, reasons, source URLs, and revision explanations. Sources are public and shared with Digger, scoped by market/query and freshness.

`POST /swarm/run` accepts `user_id`, `market_id`, and selected outcome, validates an open market and configured provider, and returns a new or freshly cached `run_id`. `GET /swarm/runs/{id}` returns status/result. `GET /swarm/runs/{id}/stream` replays persisted events after a cursor and streams new ones over SSE. Results remain readable after the worker stops. Interrupted jobs become failed/incomplete on restart.

Round 1 launches four separate calls in parallel: News Scout, Base Rate Analyst, Market Reader, and Skeptic. They cannot see one another's estimates. Market Reader receives only verified Gemini quotes, rules, volume, and genuinely available price snapshots; it has no web search tool. The other agents may use at most two searches each, only when their fresh shared evidence is insufficient.

Round 2 launches separate revision calls with all Round 1 answers. It adds no new searches. Validate probabilities in `[0,1]`, confidence, exactly three short reasons, and safe source links. Compute the median of the four revised Yes probabilities in application code. One Synthesizer call explains that fixed number and disagreements; it cannot change the aggregation.

Persist started/query/source/note/estimate/round/revision/result/error events and actual token/search usage. Proposed caps: two runs per user per hour, two simultaneous runs globally, 30-minute completed-run cache, fixed per-call output limits. Enforce atomic deduplication before launching a worker. A missing agent result prevents a complete forecast.

Track every prospective forecast. Refresh resolution from Gemini and calculate Brier score and side edge once. Exclude voids and show sample counts. Preserve an immutable market-price-at-forecast baseline. Tests cover median, schema rejection, call independence, caching, limits, failures, SSE replay, and one-time scoring. Live self-check: two distinct markets with raw provider events and differing results, without asserting that differences guarantee accuracy.

## Phase C: Visualization

Add `/swarm/{runId}` using React Flow: market center, four role nodes, Synthesizer below. State colors and debate edges derive from stored agent events. A clicked node shows brief evidence notes, actual queries, sources, and estimates. A final panel compares the computed estimate with the recorded Gemini side quote and shows the range of disagreement.

The timeline uses SSE event IDs to reconnect without duplicates. Replay walks the saved log and is clearly labeled replay; it never masquerades as a new model call. Mobile layout and keyboard access follow the existing app. Self-check requires two browser windows receiving the same actual stream; current browser automation access remains denied, so human/manual verification may be needed unless access changes.

## Phase D and Digger Phase I: Connections

Spare cards link to research and show a probability chip only when an actual completed cached run exists. Squad legs gain Ask the Swarm; a completed result is posted into that squad's chat once per request. Friend profiles compare genuinely shared resolved markets and show unavailable states for no overlap. The leaderboard reuses friends’ existing across-squad records and ranks one earliest eligible swarm forecast per instrument on their final-pick universe, with sample counts. See [implementation and self-check](SWARM_CONNECTIONS.md).

Digger articles show live related markets with actions to open a Spare choice, add a squad leg, or run the swarm. Sharing posts a short summary and original link into an explicitly chosen squad, with an optional leg vote before lock. Topic weights use real pick frequency plus sample-aware category edge, alongside onboarding interests. Never use losses to increase stakes or pursue recovery.

News and News Scout reuse the same public evidence cache. Fresh cached evidence is supplied before an agent call, and a search tool is omitted when no new research is needed. New native search results are normalized back into the cache for Digger. Two profiles with different actual histories must see different topic ordering in a controlled test.

## Phase E: Optional experiment

The sandbox trading bot is stretch work and needs a separate approval after research and visualization pass their live checks. It would use an isolated sandbox account, separate budget and journal, explicit size/daily limits, and no user roundup funds. It is not part of the initial swarm build.

## Phase F: Delivery

Update README and DEMO with roles, two rounds, median, limits, source caching, forecast scoring, and honest verification results. Include real event logs and screenshots only when actually captured. Commit each working phase, show commands/results, and wait for the user's next phase OK as explicitly requested.
