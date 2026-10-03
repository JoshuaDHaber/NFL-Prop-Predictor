#!/usr/bin/env bash
# One entry point for the project.   ./run.sh help
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"

# Prefer a Node already on PATH, then ~/.local/node, then the project-local copy.
for d in "$HOME/.local/node/bin" "$ROOT/.tools/node/bin"; do
  command -v node >/dev/null 2>&1 || { [ -x "$d/node" ] && export PATH="$d:$PATH"; }
done

py()  { (cd "$ROOT/backend" && .venv/bin/python "$@"); }
npmf() { (cd "$ROOT/frontend" && npm "$@"); }
need_node() { command -v node >/dev/null 2>&1 || { echo "Node.js not found. Install it from https://nodejs.org" >&2; exit 1; }; }
need_venv() { [ -x "$ROOT/backend/.venv/bin/python" ] || { echo "Backend not set up. Run: ./run.sh setup" >&2; exit 1; }; }

case "${1:-help}" in
  setup)    # install everything (safe to re-run)
    [ -x "$ROOT/backend/.venv/bin/python" ] || python3 -m venv "$ROOT/backend/.venv"
    "$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
    [ -f "$ROOT/backend/.env" ] || { cp "$ROOT/.env.example" "$ROOT/backend/.env"; echo "Created backend/.env: add your ODDS_API_KEY there (optional)."; }
    need_node; npmf install --no-audit --no-fund
    echo "Setup done. Next: ./run.sh refresh   then   ./run.sh start" ;;
  refresh)  # compute projections (extra args pass through, e.g. --odds none --exclude "Name")
    need_venv; shift; py -m app.cli "$@" ;;
  build)    need_node; npmf run build ;;
  start)    # API + built UI at http://localhost:$PORT
    need_venv
    [ -d "$ROOT/frontend/dist" ] || { echo "No UI build found; building..."; need_node; npmf run build; }
    echo "Open http://localhost:$PORT"
    cd "$ROOT/backend" && exec .venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT" ;;
  lan)      # same as start, but reachable from your phone (read-only from other devices)
    ts="$(ifconfig 2>/dev/null | awk '/inet 100\./{split($2,a,"."); if (a[2]>=64 && a[2]<=127) {print $2; exit}}')"
    ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
    [ -n "$ts" ] && echo "Tailscale (any network, your devices only): http://$ts:$PORT"
    echo "Same Wi-Fi:                                 http://${ip:-<your-mac-ip>}:$PORT"
    [ -z "$ts" ] && echo "Tip: install Tailscale (see README) to reach this from anywhere."
    echo "Other devices can read the app but cannot refresh data or spend API credits."
    HOST=0.0.0.0 exec "$0" start ;;
  dev)      # API (auto-reload) on :8000 and Vite on :5173 together
    need_venv; need_node
    trap 'kill 0' EXIT INT TERM
    (cd "$ROOT/backend" && exec .venv/bin/uvicorn app.main:app --reload --port 8000) &
    (cd "$ROOT/frontend" && exec npm run dev) &
    echo "UI: http://localhost:5173   API: http://localhost:8000"
    wait ;;
  test)     need_venv; need_node; py -m pytest -q; npmf test; npmf run typecheck ;;
  help|-h|--help|*)
    cat <<'H'
Usage: ./run.sh <command>

  setup     Install backend (venv) and frontend (npm) dependencies
  refresh   Compute this week's projections   [--odds none|missing|all] [--exclude "Name" ...]
  build     Build the React app
  start     Run the app at http://localhost:8000 (builds the UI if needed)
  lan       Same, but reachable from your phone on the same Wi-Fi (read-only there)
  dev       Run API + Vite dev server with live reload (UI on :5173)
  test      Run backend and frontend tests

First time:  ./run.sh setup && ./run.sh refresh && ./run.sh start
H
    ;;
esac
