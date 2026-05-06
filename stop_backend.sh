#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/branding.sh"

PID_FILE="$PREFIX/tmp/backend.pid"
PORT_FILE="$PREFIX/tmp/backend.port"
PORTD_NAME_FILE="$PREFIX/tmp/backend.portd-name"
PORTD_ADMIN="${PORTD_ADMIN:-http://localhost:2019}"

# Resolve backend port: prefer the file written by start_backend.sh (handles
# portd-allocated ports), then $FASTAPI from .ports, then default.
if [ -f "$PORT_FILE" ]; then
    BACKEND_PORT=$(cat "$PORT_FILE" 2>/dev/null)
fi
if [ -z "$BACKEND_PORT" ] && [ -f "$PREFIX/etc/.ports" ]; then
    source "$PREFIX/etc/.ports"
    BACKEND_PORT=$FASTAPI
fi
BACKEND_PORT="${BACKEND_PORT:-8000}"

echo "🛑 Stopping $BRAND_APP_NAME backend (port $BACKEND_PORT)..."

# Deregister from portd if we registered there. Best-effort.
if [ -f "$PORTD_NAME_FILE" ]; then
    PORTD_NAME=$(cat "$PORTD_NAME_FILE" 2>/dev/null)
    if [ -n "$PORTD_NAME" ] && curl -sf -o /dev/null "$PORTD_ADMIN/portd/services" 2>/dev/null; then
        DEREG_PAYLOAD=$(printf '{"name":"%s"}' "$PORTD_NAME")
        if curl -sf -o /dev/null -X DELETE "$PORTD_ADMIN/portd/deregister" \
            -H "Content-Type: application/json" -d "$DEREG_PAYLOAD" 2>/dev/null; then
            echo "📡 Deregistered \"$PORTD_NAME\" from portd"
        fi
    fi
fi

# Function to wait for PID to exit with timeout
wait_for_pid_exit() {
    local pid=$1
    local timeout=5

    echo "Waiting for process $pid to exit..."
    while [ $timeout -gt 0 ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "Process $pid has exited"
            return 0
        fi
        sleep 1
        timeout=$((timeout - 1))
    done

    echo "Process $pid still running, sending SIGKILL"
    kill -KILL "$pid" 2>/dev/null

    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        echo "WARNING: Process $pid still running after SIGKILL"
        return 1
    else
        echo "Process $pid terminated with SIGKILL"
        return 0
    fi
}

# Method 1: Saved PID file (most reliable)
if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "Killing backend process $pid from PID file"
        kill -TERM "$pid" 2>/dev/null
        wait_for_pid_exit "$pid"
    else
        echo "PID file exists but process $pid not running"
    fi
    rm -f "$PID_FILE"
else
    echo "No PID file found at $PID_FILE"
fi

# Method 2: Port-based lookup (fallback)
pid=$(lsof -ti:"$BACKEND_PORT" 2>/dev/null)
if [ -n "$pid" ]; then
    echo "Sending SIGTERM to backend process $pid listening on port $BACKEND_PORT"
    kill -TERM $pid 2>/dev/null
    for p in $pid; do wait_for_pid_exit "$p"; done
else
    echo "No backend process found on port $BACKEND_PORT"
fi

# Method 3: PREFIX-scoped main.py cleanup
echo "Checking for remaining main.py processes using $PREFIX venv..."
main_pids=$(pgrep -f "$PREFIX/venv/bin/python3.*main\.py")
if [ -n "$main_pids" ]; then
    echo "Found main.py processes for this PREFIX: $main_pids"
    for pid in $main_pids; do
        echo "Killing main.py process $pid"
        kill -TERM "$pid" 2>/dev/null
        wait_for_pid_exit "$pid"
    done
else
    echo "No main.py processes found for this PREFIX"
fi

# Clean up dispatcher-worker processes for THIS PREFIX
echo "Checking for remaining dispatcher-worker processes for this PREFIX..."
worker_pids=$(pgrep -f "$PREFIX/venv/bin/.*dispatcher-worker")
if [ -n "$worker_pids" ]; then
    echo "Found dispatcher-worker processes for this PREFIX: $worker_pids"
    for pid in $worker_pids; do
        echo "Killing dispatcher-worker process $pid"
        kill -TERM "$pid" 2>/dev/null
        sleep 2
        if kill -0 "$pid" 2>/dev/null; then
            echo "dispatcher-worker process $pid still running, sending SIGKILL"
            kill -KILL "$pid" 2>/dev/null
        fi
    done
else
    echo "No dispatcher-worker processes found for this PREFIX"
fi

# Worker port cleanup
echo "Checking for processes on worker ports..."
for port in 8501 8502 8503 8504 8505; do
    pid=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pid" ]; then
        echo "Killing process $pid on worker port $port"
        kill -TERM $pid 2>/dev/null
        sleep 1
        if kill -0 $pid 2>/dev/null; then
            kill -KILL $pid 2>/dev/null
        fi
    fi
done

# Cleanup state files
rm -f "$PORT_FILE" "$PORTD_NAME_FILE" 2>/dev/null || true

echo "✅ Backend stop complete"
exit 0
