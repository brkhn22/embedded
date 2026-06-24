#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${YOLO_WEB_PORT:-8001}"

if command -v lsof >/dev/null 2>&1; then
  if lsof -iTCP:"$PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
    echo "YOLO web server zaten calisiyor: http://localhost:${PORT}"
    echo "Farkli bir port isterseniz: YOLO_WEB_PORT=8002 ./yolo/start_web.sh"
    exit 0
  fi
fi

exec .venv/bin/python -c "from yolo.control_server import run_yolo_server; run_yolo_server(port=${PORT})"
