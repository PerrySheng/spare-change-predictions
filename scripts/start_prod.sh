#!/bin/sh
set -eu
mkdir -p /data
cd /app/backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers --forwarded-allow-ips='*' --no-access-log
