#!/bin/zsh
# WebVid — start backend + frontend on non-common ports (4819 / 4820)
# Per user requirement: avoid ports used by other projects.

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=4819
FRONTEND_PORT=4820
LOG_DIR="/tmp"
BACKEND_LOG="${LOG_DIR}/webvid-backend.log"
FRONTEND_LOG="${LOG_DIR}/webvid-frontend.log"
KEEPER_LOG="${LOG_DIR}/webvid-keeper.log"

echo "────────────────────────────────────────────────────────"
echo "  WebVid  •  Websites → Short Videos (V0.1)"
echo "  Backend:  http://localhost:${BACKEND_PORT}"
echo "  Frontend:  http://localhost:${FRONTEND_PORT}"
echo "  Keeper:   ${KEEPER_LOG}"
echo "  Logs:     ${BACKEND_LOG}  +  ${FRONTEND_LOG}"
echo "────────────────────────────────────────────────────────"

# Kill anything that might be sitting on our ports (safe)
lsof -ti :${BACKEND_PORT} | xargs kill -9 2>/dev/null || true
lsof -ti :${FRONTEND_PORT} | xargs kill -9 2>/dev/null || true
pkill -f 'webvid-keeper.sh' 2>/dev/null || true
sleep 0.4

cd "$ROOT"

# Start the keeper (which manages backend + frontend with auto-restart on port loss)
echo "→ Starting keeper (auto-heals servers on 4819/4820)..."
nohup sh -c 'trap "" TERM INT; exec ./keeper.sh' > "${KEEPER_LOG}" 2>&1 &
KEEPER_PID=$!

cd "$ROOT"
sleep 1.5

echo ""
echo "✓ Keeper running (will start/keep backend on ${BACKEND_PORT} + frontend on ${FRONTEND_PORT})."
echo "  Open: http://localhost:${FRONTEND_PORT}"
echo ""
echo "Tip: For true MP4 (not just GIF fallback):"
echo "  brew install ffmpeg"
echo ""
echo "To stop everything: pkill -f 'webvid-keeper.sh|4819|4820'"
echo ""
echo "Logs:"
echo "  Keeper:   tail -f /tmp/webvid-keeper.log"
echo "  Backend:  tail -f ${BACKEND_LOG}"
echo "  Frontend: tail -f ${FRONTEND_LOG}"
echo ""
echo "Note: In this chat/agent, background tasks have a ~5min lifetime."
echo "      The keeper will auto-restart servers inside its window."
echo "      For fully independent persistent use, run this script in a dedicated terminal."

# If this script is run directly (not under agent monitor), keep it attached
if [ -t 0 ]; then
  trap "echo 'Stopping...'; kill ${KEEPER_PID} 2>/dev/null || true; pkill -f 'webvid-keeper.sh|4819|4820' 2>/dev/null || true; exit" INT TERM
  wait
else
  echo "(Detached / background mode)"
fi