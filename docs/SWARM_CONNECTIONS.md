# Swarm connections — Phase D

The user approved Phase D on October 11, 2026. The implementation is built and its controlled integration checks pass. Google Gemini + Context.dev forecasts and an actual Railway researched-leg/share flow are verified; Claude and browser click-through checks remain unverified. No example forecast is inserted into the running app.

## Try it

From the project root, run `./run.sh`, then open `http://127.0.0.1:8000`.

1. Configure `SWARM_PROVIDER=gemini`, `GOOGLE_AI_API_KEY`, and `CONTEXT_DEV_API_KEY` to use the demo’s verified Google + Context.dev path. Set `SWARM_PROVIDER=anthropic` with `ANTHROPIC_API_KEY` for the alternative Claude path. Never paste a key into the UI or commit it.
2. In Spare or News, open **Swarm research** on a live Gemini contract. A finished result appears as a cached chip showing the selected side's probability and its Gemini quote **at forecast time**. Opening the chip reads the saved run; it does not pay for another call.
3. In **Group betting**, add a leg and press **Ask the Swarm · share to chat**. The server saves the share request. When the real worker finishes, the short research summary and probability comparison appear in **Chat**, attached to that leg, even if the requester closed the workspace. Cached completed research can be shared with no provider key. A failed run posts an error without a probability.
4. A squad member can open that shared result and replay its saved events. Unshared runs remain on the owner-only route; outsiders cannot use the squad route.
5. Research before the squad locks its picks. After Gemini publishes the result, use **Check Gemini results**, open **Track records**, and choose your profile. **You vs the Swarm** compares only markets that both forecasted and that resolved in this squad.

Chips refresh on returning from the workspace and once per minute while the page is visible. Their backend cache expires after 30 minutes. Historical chat and accuracy records remain available after cache expiry. A chip compares against the saved quote, not the newest trading quote.

## Fair scoring

The Swarm is ranked by the same average `hit − observed buy quote` formula as friends. Its predicted side is Yes when its Yes probability is at least 50%, otherwise No. The corresponding side quote must exist in the recorded Gemini snapshot. Missing No quotes are never replaced with `1 − Yes quote`.

For the leaderboard, each instrument contributes at most one forecast: the earliest completed run from the current squad's members, before the first lock of their final picks on that instrument and before the market closed. Runs completed later, failed runs, replaced picks, unrelated users' runs, voids, and missing prices cannot improve edge. Profile comparisons use that same canonical run for the member's visible legs, and require that exact run to have been explicitly shared into this squad. An unshared earlier run leaves the comparison unavailable; sharing a favorable later rerun cannot replace it. Repeated research cannot cherry-pick a better estimate or multiply a score.

Friends retain their existing records across squads. The Swarm's market sample covers those members' final picks with eligible research, so sample sizes can differ. The profile card uses the same resolved markets on both sides for a closer comparison. It shows an empty state when there is no overlap. Scores are descriptive and small samples do not establish skill.

## API additions

| Endpoint | Body / result |
| --- | --- |
| `POST /squads/{squad_id}/swarm/ask` | `{user_id, leg_id}`; reuses an exact-side completed cache or starts real research, saves a share intent, returns `{run_id,status,squad_id,leg_id}`. |
| `POST /squads/{squad_id}/swarm/share` | `{user_id, leg_id, run_id}`; explicitly shares the owner's completed run for the same contract and side. |
| `GET /squads/{squad_id}/swarm/runs/{run_id}?user_id=...` | Member-only access to an explicitly posted completed run, including its stored events for replay. |

Squad details include a `kind: "swarm"` leaderboard row, plus `record.swarm_comparison` on each friend. `swarm_shares` stores a unique `(squad_id,leg_id,run_id)` intent. Posting uses the existing persisted SquadEvent/SSE channel, inside a serialized transaction, so callbacks and retries cannot duplicate chat entries. Startup reconciles interrupted/completed pending shares without starting model calls.

The existing user UUID mechanism remains a local demo identity, not production authentication. All provider secrets stay on the server. This integration cannot place a trade or change a leg, vote, stake, or roundup allocation.

## Self-check

```sh
.venv/bin/python -m pytest -q -c backend/pytest.ini backend/tests/test_swarm_connections.py
npm --prefix frontend run build
```

Twelve focused controlled tests cover earliest forecast selection, lock timing, unrelated-user isolation, missing side quotes, exact-side sharing, membership, completed-only access, cached asks without credentials, real worker completion callbacks, failure handling, concurrent/idempotent posting, and void/replaced pick exclusion. The full backend suite has 195 passing tests; 17 Node tests and the production build pass.

The original Claude-specific check remains unverified, but the user-selected Google provider completed real research. A completed forecast became the caller’s own NO leg, funded SPC escrow, posted to squad chat, and was opened by another member on Railway. [Cloud evidence](RAILWAY_SWARM_CHECK.json). Swarm contributes no money or membership slot. Browser permission was previously denied, so rendered layout and multi-window click-through checks are not claimed. The separate sandbox trading bot remains disabled and outside this approved phase.
