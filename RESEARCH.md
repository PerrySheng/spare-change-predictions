# Forecasting swarm research

Phase A research, October 11, 2026. This is a proposed implementation, not evidence that the app's swarm has run. No Anthropic API key has been supplied.

## Relevant papers and projects

| Source | What it contributes | Application here |
| --- | --- | --- |
| [Approaching Human-Level Forecasting with Language Models, Halawi et al.](https://arxiv.org/abs/2402.18563) and [author implementation](https://github.com/dannyallover/llm_forecasting) | Retrieval, individual forecasts, and aggregation evaluated against human forecasts. | Separate public evidence retrieval from estimation; retain evidence timestamps. Do not copy the codebase. |
| [Wisdom of the Silicon Crowd](https://arxiv.org/abs/2402.19379) | Aggregated forecasts from multiple language models, including a reported bias toward positive answers. | Preserve the initial estimates and measure calibration; do not assume that four roles using one model are four independent experts. |
| [ForecastBench](https://arxiv.org/abs/2409.19839) and [benchmark project](https://www.forecastbench.org/) | A changing set of future questions with human comparisons, designed to reduce answer leakage. | Record forecasts before resolution and score them afterward; exclude retrospective estimates from the leaderboard. |
| [Large Language Model Prediction Capabilities: Evidence from a Real-World Forecasting Tournament](https://arxiv.org/abs/2310.13014) | Prospective evaluation in a forecasting tournament. | Judge accuracy on resolved future events rather than a few appealing demos. |
| [Improving Factuality and Reasoning through Multiagent Debate](https://arxiv.org/abs/2305.14325) | Agents first answer and then critique other answers. Its results concern reasoning tasks, not proof of profitable market forecasts. | Keep independent Round 1 estimates, then conduct one bounded debate round. Treat benefit as a hypothesis to evaluate. |
| [Metaculus forecasting-tools](https://github.com/Metaculus/forecasting-tools) | Forecasting utilities, API wrappers, aggregation, and cost tracking. | Use its architecture as a reference for validation and measurement; keep our FastAPI/SQLite app and Anthropic TypeScript requirement. |
| [React Flow](https://reactflow.dev/learn) | Controlled graph nodes and edges for interactive visualizations. | Drive node state from persisted run events; use the same log for reconnection and replay. |

## Current provider contracts

The [Claude model catalog](https://platform.claude.com/docs/en/models/overview) currently lists `claude-sonnet-5-5`. Use a configurable `ANTHROPIC_MODEL` with that documented default, then verify access and capabilities through the Models API when credentials are configured. This is a proposed application setting, not a change to the coding agent's model.

The [official TypeScript SDK](https://github.com/anthropics/anthropic-sdk-typescript) supports streaming Messages calls. The [web search documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool) documents `web_search_20250305` for basic search, `web_search_20260318` for newer filtering, `max_uses`, `server_tool_use` query blocks, and search-result blocks with source metadata. Start with basic search and a two-search cap per research agent. Validate the installed SDK's types and account capabilities before a paid call. Do not display hidden thinking; show brief evidence notes and the explicit three reasons requested in the output schema.

## Findings and pitfalls

Independent estimates before discussion preserve a useful baseline. Debate can still create anchoring or agreement without accuracy. Keep both rounds, each change explanation, and the final range of estimates. A median is simple to audit and limits one extreme estimate's influence; for four values it is the mean of the middle two. This choice is an engineering recommendation, not a claim that median always beats other aggregators.

Sources need publication/retrieval dates and links. Never infer that a cited article proves a forecast. Prices are executable quotes, not perfectly calibrated probabilities. Record both side prices and clearly identify which side the forecast concerns. Do not invent historical odds when Gemini has not supplied them.

Brier score for a Yes forecast is `(p_yes - resolved_yes)^2`. Lower is better. Edge for the side selected by the forecast is `hit - that_side_buy_price_at_forecast`. A positive edge on a small sample does not establish a reliable strategy. Voids are reported separately, and comparisons use only the same resolved markets and comparable forecast times.

Limit cost with nine model calls at most per run: four independent calls, four debate calls, and one summary call. Search only during the independent round, with no search tool for Market Reader. Cache a completed market run for 30 minutes, enforce per-user and global quotas, cap output tokens, and record provider token/search usage. If one agent fails or returns invalid JSON, mark the run incomplete instead of manufacturing a final estimate.

## Current codebase

Gemini discovery, fresh execution quotes, signing, and sandbox guards live in `backend/app/providers.py`. `scoring.py` deterministically ranks markets and exposes actual Yes/No quotes. `main.py` owns purchases, caps, paper/sandbox allocations, settlement, and Context.dev reading. `context_reading.py` already caches public search metadata; no customer purchase history is sent to that provider.

The frontend is a React PWA. This task is adding Group betting, Spare, and News tabs, SQLite-backed squads, per-leg votes/chat, persisted SSE events, and track records. There was no prior swarm, Squad Slip, or SSE implementation in the original app. The proposed swarm should reuse the new event pattern and existing Gemini adapter rather than replace them.

News/Digger should use real category pick counts and resolved category edge to order topics. Article summaries stay short and link to the original source. A shared public evidence cache can feed News and the future News Scout. Native Anthropic searches cannot be intercepted by our cache, so avoid calling the search tool when fresh cached evidence already covers the market, and do not promise that arbitrary new server-side searches will always be deduplicated.
