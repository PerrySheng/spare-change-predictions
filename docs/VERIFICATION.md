# Verification record

Checked on October 11, 2026. This is a local hackathon MVP, with paper mode enabled by default.

| Check | Result |
| --- | --- |
| Backend suite | 60 tests passed. One dependency deprecation warning from Starlette's TestClient/httpx integration. |
| Frontend production build | Passed with Vite 7.3.7. |
| Python dependency consistency | `pip check` passed. |
| Launch script syntax | `bash -n run.sh` passed. |
| Local server | `/health`, `/`, both built assets, manifest, and service worker returned HTTP 200. |
| Public Gemini data | Retrieved real production and sandbox prediction-market quotes. |
| Paper flow with public data | Two isolated profiles produced sports and crypto suggestions, fee-aware paper allocations, and dashboard valuations using Gemini responses. Test databases were temporary. |
| Context.dev without credentials | Returned an actionable HTTP 503 mentioning `CONTEXT_DEV_API_KEY`; no substitute reading materials. |
| Review | Backend accounting/provider review and frontend integration review completed; reported correctness issues were fixed. |

The backend tests cover currency parsing, roundup arithmetic, fees and whole-contract grids, deterministic ranking, user separation, purchase idempotency, single allocation, caps and pausing, price changes, displayed quantity/cost limits, rollover pooling, settlement credited once, Plaid modifications/removals, sandbox reservations/rejections, and Context.dev response validation and failure handling. Provider fixtures verify local behavior without proving authenticated access.

No private provider credentials were supplied. Actual Context.dev retrieval, Plaid Sandbox ingestion/webhook delivery, and Gemini sandbox order execution remain unverified. These paths need the corresponding keys in the root `.env` and a backend restart. Production money trading is disabled.

Browser access to the local preview was denied by the tool's permission check. Rendered layout and interaction have therefore not been verified in-browser. iPhone Shortcut triggers and PWA installation also remain untested on a device. The manifest and assets are served, but that alone does not confirm installation.

Reproduce local checks from the project root:

```sh
.venv/bin/python -m pytest -q -c backend/pytest.ini backend/tests
.venv/bin/python -m pip check
bash -n run.sh
cd frontend
npm run build
```

Follow [README.md](../README.md) for configuration and [DEMO.md](../DEMO.md) for the walkthrough. Provider spike commands can create sandbox test data or orders when keys are supplied; review their documented behavior before running them.
