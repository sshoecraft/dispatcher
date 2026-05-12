#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/branding.sh"
backend_dir=backend

# Load port configuration
if [ -f "$PREFIX/etc/.ports" ]; then
    source "$PREFIX/etc/.ports"
fi

PID_FILE="$PREFIX/tmp/backend.pid"
PORT_FILE="$PREFIX/tmp/backend.port"
PORTD_NAME_FILE="$PREFIX/tmp/backend.portd-name"

# Ensure runtime dirs exist (portd mode skips setup.sh; this is harmless if
# they already exist).
mkdir -p "$PREFIX/etc" "$PREFIX/logs" "$PREFIX/tmp"

# portd integration. If portd is up on :2019, ask it to allocate a port and
# register us so the frontend (and any other client) can reach us via portd's
# path-based routing without coordinating port numbers. If portd is down, fall
# back to $FASTAPI from .ports.
PORTD_ADMIN="${PORTD_ADMIN:-http://localhost:2019}"
PORTD_BACKEND_NAME="${PORTD_BACKEND_NAME:-${BRAND_SLUG}-backend}"
USE_PORTD=false
if curl -sf -o /dev/null "$PORTD_ADMIN/portd/services" 2>/dev/null; then
    USE_PORTD=true
fi

if [ "$USE_PORTD" = "true" ] && [ -z "${BACKEND_PORT:-}" ]; then
    echo "🛰  portd detected at $PORTD_ADMIN — requesting port allocation..."
    ALLOC_PAYLOAD=$(printf '{"name":"%s"}' "$PORTD_BACKEND_NAME")
    ALLOC_RESP=$(curl -sf -X POST "$PORTD_ADMIN/portd/allocate" \
        -H "Content-Type: application/json" -d "$ALLOC_PAYLOAD" 2>/dev/null || true)
    if [ -z "$ALLOC_RESP" ]; then
        echo "❌ Error: portd /portd/allocate request failed"
        exit 1
    fi
    BACKEND_PORT=$(echo "$ALLOC_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['port'])" 2>/dev/null || true)
    if [ -z "$BACKEND_PORT" ]; then
        echo "❌ Error: could not parse port from portd response: $ALLOC_RESP"
        exit 1
    fi
    echo "🎯 portd allocated and registered \"$PORTD_BACKEND_NAME\" on port $BACKEND_PORT"
    # FastAPI needs to know the public-facing prefix to generate correct URLs
    # (Swagger's openapi.json link, etc.) when fronted by portd path routing.
    export UVICORN_ROOT_PATH="/$PORTD_BACKEND_NAME"
else
    BACKEND_PORT="${BACKEND_PORT:-${FASTAPI:-8000}}"
    if [ "$USE_PORTD" = "true" ]; then
        echo "🛰  portd detected, but BACKEND_PORT=$BACKEND_PORT was set explicitly — using it"
    fi
fi

# Make the chosen port visible to the backend process so info.port
# (which reads $FASTAPI) matches the actual listener. Workers use
# info.port to build their --backend-url callback target.
export FASTAPI="$BACKEND_PORT"

# Refuse to start if backend is already running
if [ -f "$PID_FILE" ]; then
    EXISTING_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
        echo "❌ Error: Backend already running (PID $EXISTING_PID). Run stop_backend.sh first."
        exit 1
    fi
    rm -f "$PID_FILE"
fi

cd "$SCRIPT_DIR/${backend_dir}" || exit 1

# Set environment variables (similar to Docker ENV)
export PYTHONUNBUFFERED=1
export PYTHONPYCACHEPREFIX="$PREFIX/tmp/__pycache__"

# Activate venv so subprocesses can find venv binaries (like dispatcher-worker)
source "$PREFIX/venv/bin/activate"

# Start server in background
python3 main.py "$BACKEND_PORT" > "$PREFIX/logs/backend.log" 2>&1 &
BACKEND_PID=$!

echo "$BACKEND_PID" > "$PID_FILE"
echo "$BACKEND_PORT" > "$PORT_FILE"
if [ "$USE_PORTD" = "true" ]; then
    echo "$PORTD_BACKEND_NAME" > "$PORTD_NAME_FILE"
else
    rm -f "$PORTD_NAME_FILE" 2>/dev/null || true
fi

echo "Backend started with PID: $BACKEND_PID on port $BACKEND_PORT"
echo "Logs: $PREFIX/logs/backend.log"
if [ "$USE_PORTD" = "true" ]; then
    echo "portd: registered as \"$PORTD_BACKEND_NAME\" (root_path=$UVICORN_ROOT_PATH)"
fi
