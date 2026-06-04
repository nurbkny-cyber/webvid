#!/bin/zsh
# WebVid keeper: auto-restarts backend (4819) + frontend (4820) if their ports disappear.
# Designed to be nohup'ed. Traps signals for resilience under monitors.
trap '' TERM INT HUP

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BLOG="${ROOT}/../.cache/webvid-backend.log"  # or just use /tmp
# Use /tmp for logs to keep project clean
BLOG="/tmp/webvid-backend.log"
FLOG="/tmp/webvid-frontend.log"
KLOG="/tmp/webvid-keeper.log"

# Load .env if present (supports XAI_API_KEY, GROK_API_KEY, etc. for the child server processes)
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ROOT/.env"
  set +a
fi

mkdir -p "$(dirname "$BLOG")" 2>/dev/null || true

echo "[keeper] started at $(date)" >> "$KLOG"

while true; do
  if ! lsof -i:4819 >/dev/null 2>&1; then
    echo "[keeper] restarting backend at $(date)" >> "$KLOG"
    cd "$ROOT"
    nohup sh -c 'trap "" TERM INT; exec python3 backend/server.py' > "$BLOG" 2>&1 &
  fi
  if ! lsof -i:4820 >/dev/null 2>&1; then
    echo "[keeper] restarting frontend at $(date)" >> "$KLOG"
    cd "$ROOT/frontend"
    nohup sh -c 'trap "" TERM INT; exec python3 -m http.server 4820' > "$FLOG" 2>&1 &
  fi
  sleep 25
done
