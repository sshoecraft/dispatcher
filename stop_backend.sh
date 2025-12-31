#!/bin/bash

PREFIX=${PREFIX:-${HOME}/.dispatcher}

# Load port configuration
if [ -f "$PREFIX/etc/.ports" ]; then
    source "$PREFIX/etc/.ports"
    BACKEND_PORT=$FASTAPI
else
    # Fallback to default
    BACKEND_PORT=8000
fi

# Function to wait for PID to exit with timeout
wait_for_pid_exit() {
    local pid=$1
    local timeout=5

    echo "Waiting for process $pid to exit..."
    while [ $timeout -gt 0 ]; do
        if ! kill -0 $pid 2>/dev/null; then
            echo "Process $pid has exited"
            return 0
        fi
        sleep 1
        timeout=$((timeout - 1))
    done

    # Process still running after timeout, send KILL
    echo "Process $pid still running, sending SIGKILL"
    kill -KILL $pid 2>/dev/null
    
    # Wait a bit more for KILL to take effect
    sleep 1
    if kill -0 $pid 2>/dev/null; then
        echo "WARNING: Process $pid still running after SIGKILL"
        return 1
    else
        echo "Process $pid terminated with SIGKILL"
        return 0
    fi
}

# Method 1: Try to kill using saved PID file (most reliable)
if [ -f "$PREFIX/tmp/backend.pid" ]; then
    pid=$(cat "$PREFIX/tmp/backend.pid" 2>/dev/null)
    if [ ! -z "$pid" ] && kill -0 $pid 2>/dev/null; then
        echo "Killing backend process $pid from PID file"
        kill -TERM $pid 2>/dev/null
        wait_for_pid_exit $pid
        rm -f "$PREFIX/tmp/backend.pid"
    else
        echo "PID file exists but process $pid not running"
        rm -f "$PREFIX/tmp/backend.pid"
    fi
else
    echo "No PID file found at $PREFIX/tmp/backend.pid"
fi

# Method 2: Find and kill process listening on backend port (fallback)
pid=$(lsof -ti:$BACKEND_PORT 2>/dev/null)
if [ ! -z "$pid" ]; then
    echo "Sending SIGTERM to backend process $pid listening on port $BACKEND_PORT"
    kill -TERM $pid 2>/dev/null
    wait_for_pid_exit $pid
else
    echo "No backend process found on port $BACKEND_PORT"
fi

# Method 3: Find and kill any remaining main.py processes using THIS PREFIX's venv (final cleanup)
echo "Checking for remaining main.py processes using $PREFIX venv..."
main_pids=$(pgrep -f "$PREFIX/venv/bin/python3.*main\.py")
if [ ! -z "$main_pids" ]; then
    echo "Found main.py processes for this PREFIX: $main_pids"
    for pid in $main_pids; do
        echo "Killing main.py process $pid"
        kill -TERM $pid 2>/dev/null
        wait_for_pid_exit $pid
    done
else
    echo "No main.py processes found for this PREFIX"
fi

# Clean up any remaining dispatcher-worker processes for THIS PREFIX
echo "Checking for remaining dispatcher-worker processes for this PREFIX..."
worker_pids=$(pgrep -f "$PREFIX/venv/bin/.*dispatcher-worker")
if [ ! -z "$worker_pids" ]; then
    echo "Found dispatcher-worker processes for this PREFIX: $worker_pids"
    for pid in $worker_pids; do
        echo "Killing dispatcher-worker process $pid"
        kill -TERM $pid 2>/dev/null
        sleep 2
        if kill -0 $pid 2>/dev/null; then
            echo "dispatcher-worker process $pid still running, sending SIGKILL"
            kill -KILL $pid 2>/dev/null
        fi
    done
else
    echo "No dispatcher-worker processes found for this PREFIX"
fi

# Clean up any processes on worker ports (8501, 8502, etc)
echo "Checking for processes on worker ports..."
for port in 8501 8502 8503 8504 8505; do
    pid=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$pid" ]; then
        echo "Killing process $pid on worker port $port"
        kill -TERM $pid 2>/dev/null
        sleep 1
        if kill -0 $pid 2>/dev/null; then
            kill -KILL $pid 2>/dev/null
        fi
    fi
done

echo "Backend stop complete"
exit 0