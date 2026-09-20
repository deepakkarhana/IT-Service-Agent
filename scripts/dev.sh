#!/usr/bin/env bash
# macOS / Linux equivalent of dev.ps1. Starts backend and frontend together.
#
#   bash scripts/dev.sh            # backend on 8020
#   BACKEND_PORT=8030 bash scripts/dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PORT="${BACKEND_PORT:-8020}"

if [ ! -d .venv ]; then
  echo "==> Creating virtual environment"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install -r backend/requirements.txt
fi
[ -d frontend/node_modules ] || (cd frontend && npm install --no-audit --no-fund)
[ -f .env ] || cp .env.example .env

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "==> Backend  : http://127.0.0.1:$PORT"
./.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT" --reload &

sleep 2
echo "==> Frontend : http://localhost:5173"
(cd frontend && VITE_API_TARGET="http://127.0.0.1:$PORT" npm run dev)
