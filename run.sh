#!/usr/bin/env bash
# Starts PackCheck without auto-reload.
cd "$(dirname "$0")"
[ -f .venv/bin/activate ] && . .venv/bin/activate
echo "Open http://localhost:8000  (Ctrl+C to stop)"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
