# Railway public paper/Testnet demo

Public source: https://github.com/PerrySheng/spare-change-predictions

Live URL: https://spare-production.up.railway.app

Railway builds the root Dockerfile, which packages the React frontend, FastAPI API, Google/Claude TypeScript worker, and XRPL executor in one service. The `/data` volume stores SQLite at `sqlite:////data/spare_change.db`. Keep **one replica and one Uvicorn worker**; this MVP is not designed for multiple database replicas. The generated domain targets port 8080, matching Railway's runtime `PORT`.

Server variables: `APP_ENV=production`, `APP_PUBLIC_DEMO=true`, `TRADING_MODE=paper`, `PLAID_ENV=sandbox`, `XRPL_NETWORK=testnet`, `SWARM_PROVIDER=gemini`, `GOOGLE_AI_MODEL=gemini-3.5-flash-lite`, `DATABASE_URL=sqlite:////data/spare_change.db`. Supply provider credentials through Railway Variables. Never include `.env` in the uploaded source. `GOOGLE_AI_API_KEY` is distinct from the Gemini exchange key.

Preserve `XRPL_WALLET_KEY`, `APP_SESSION_SECRET`, and the database across redeploys. The first encrypts custodial wallet seeds and escrow fulfillments; replacing it would prevent access to existing test wallets. The session secret signs browser access/profile cookies. Keep backups private. No key values belong in documentation or reports.

For public testers, open the **same deployed URL**, create a profile, and share a squad invite through Group betting. No shared access code is required in public mode. Each device/profile gets its own signed profile cookie; another user’s ID is not sufficient to act as them. These are demo profiles without account recovery. Localhost and Railway use separate databases and invite codes. Set APP_PUBLIC_DEMO=false to restore the private friend gate; valid open squad invites also open that gate and prefill joining.

Deploy via the Railway CLI after committing and testing changes. Upload a clean staging directory containing only tracked source with `railway up <staging-path> --path-as-root --service spare --detach`. `.railwayignore` and `.dockerignore` exclude private files, databases, local dependencies and working files. Check build/deployment status, then `/health` before sharing an update.

Google free-tier calls are paced and do not enable paid Google Search. Context.dev supplies the news metadata; its billing is separate. Google account quotas and temporary provider capacity can still interrupt research. Failed runs show errors and cannot create a researched leg. Trading is paper; XRPL wallets and SPC collateral use Testnet. Full finalized-market-to-squad-payout validation remains outstanding.

HTTP multiplayer evidence is in `RAILWAY_MULTIPLAYER_CHECK.json`; real forecast evidence is in `SWARM_GOOGLE_LIVE_CHECK.json`. A status of `not_verified` is not a successful check. Browser rendering and two-window visualization were not exercised because preview access was denied.
