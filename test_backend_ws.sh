#!/usr/bin/env bash
# Start DispWatter backend only if it is not already listening, then smoke-test
# the device and panel WebSocket routes without changing application data.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
PID_DIR="$ROOT_DIR/.pids"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$PID_DIR/backend.pid"
LOG_FILE="$LOG_DIR/backend.log"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: backend virtualenv missing at $PYTHON_BIN" >&2
  echo "Create it and install backend/requirements.txt first." >&2
  exit 1
fi
mkdir -p "$PID_DIR" "$LOG_DIR"

PORT="$(cd "$ROOT_DIR" && "$PYTHON_BIN" - <<'PY'
from dotenv import dotenv_values
print(dotenv_values("backend/.env").get("PORT") or "8765")
PY
)"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "ERROR: invalid backend PORT in backend/.env: $PORT" >&2
  exit 1
fi

if ! "$PYTHON_BIN" - "$PORT" <<'PY'
import socket, sys
try:
    with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=0.5):
        pass
except OSError:
    raise SystemExit(1)
PY
then
  echo "Backend is down; starting it on port $PORT..."
  cd "$ROOT_DIR"
  "$PYTHON_BIN" -m backend.main >> "$LOG_FILE" 2>&1 &
  BACKEND_PID=$!
  echo "$BACKEND_PID" > "$PID_FILE"

  ready=0
  for _ in $(seq 1 60); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "ERROR: backend exited during startup. Recent log:" >&2
      tail -n 60 "$LOG_FILE" >&2 || true
      exit 1
    fi
    if "$PYTHON_BIN" - "$PORT" <<'PY' >/dev/null 2>&1
import socket, sys
with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=0.5):
    pass
PY
    then
      ready=1
      break
    fi
    sleep 0.5
  done
  if (( ! ready )); then
    echo "ERROR: backend did not listen on port $PORT within 30 seconds." >&2
    tail -n 60 "$LOG_FILE" >&2 || true
    exit 1
  fi
  echo "Backend started (PID $BACKEND_PID). It will be left running."
else
  echo "Backend already has a listener on port $PORT; leaving it untouched."
fi

cd "$ROOT_DIR"
"$PYTHON_BIN" - "$PORT" <<'PY'
import asyncio
import sys
import websockets

port = int(sys.argv[1])

async def test_device_route():
    uri = f"ws://127.0.0.1:{port}/ws/device"
    async with websockets.connect(uri, open_timeout=5, close_timeout=2) as ws:
        # Invalid hello deliberately avoids creating a DB row; receiving the
        # handler's validation response proves the device route is working.
        await ws.send('{"event":"hello"}')
        response = await asyncio.wait_for(ws.recv(), timeout=5)
        import json
        message = json.loads(response)
        assert message.get("event") == "auth_status", message
        assert message.get("error") == "invalid_device_id", message
    print("PASS: /ws/device WebSocket upgrade and device handler responded")

async def test_panel_route():
    uri = f"ws://127.0.0.1:{port}/ws/panel"
    async with websockets.connect(
        uri,
        extra_headers={"Origin": "http://localhost:3000"},
        open_timeout=5,
        close_timeout=2,
    ) as ws:
        # Unauthenticated ping should be rejected by application auth, proving
        # both the route and its auth gate respond. No DB writes are performed.
        await ws.send('{"event":"ping"}')
        response = await asyncio.wait_for(ws.recv(), timeout=5)
        import json
        message = json.loads(response)
        assert message.get("event") == "error", message
        assert message.get("code") == "unauthorized", message
    print("PASS: /ws/panel WebSocket upgrade and auth gate responded")

async def main():
    await test_device_route()
    await test_panel_route()
    print("WebSocket smoke test passed; this did not test ESP32 Wi-Fi, credentials, or device claim.")

asyncio.run(main())
PY
