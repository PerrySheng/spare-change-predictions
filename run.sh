#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -x "$task_root/.venv/bin/python" ]]; then
  echo "Install dependencies first using README.md. The project needs .venv/bin/python."
  exit 1
fi
if [[ ! -d "$task_root/frontend/node_modules" ]]; then
  echo "Run npm ci in frontend first."
  exit 1
fi
cd "$task_root/frontend"
npm run build
cd "$task_root/backend"
exec "$task_root/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "${SPARE_PORT:-8000}"
