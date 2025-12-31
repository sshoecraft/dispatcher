#!/bin/bash
# Automatic startup script for Dispatcher
# Starts backend, waits for it to be ready, then starts frontend

set -e

# Get the directory where this script is located (the repo directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CWD="$SCRIPT_DIR"

# Set PREFIX - expand ~ to actual home directory
export PREFIX="${PREFIX:-$HOME/.dispatcher}"

# Ensure PATH includes common locations for tools
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Load port configuration
if [[ -f "$PREFIX/etc/.ports" ]]; then
    source "$PREFIX/etc/.ports"
else
    echo "ERROR: Port configuration not found at $PREFIX/etc/.ports"
    echo "Run setup.sh first."
    exit 1
fi

LOG_DIR="$PREFIX/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

echo "Starting Dispatcher at $(date)"

# Start backend
echo "Starting backend..."
cd "$CWD"
./start_backend.sh > "$BACKEND_LOG" 2>&1 &

# Poll backend log for startup completion
echo "Waiting for backend to be ready..."
MAX_ATTEMPTS=60
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if [ -f "$BACKEND_LOG" ]; then
        # Check for success
        if grep -q "Application startup complete" "$BACKEND_LOG"; then
            echo "Backend startup complete!"
            break
        fi
        # Check for failure
        if grep -q "Address already in use\|Traceback (most recent call last)\|OSError:\|RuntimeError:" "$BACKEND_LOG"; then
            echo "ERROR: Backend failed to start. Check $BACKEND_LOG"
            tail -20 "$BACKEND_LOG"
            exit 1
        fi
    fi
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        echo "ERROR: Backend failed to start within timeout"
        echo "Last lines of log:"
        tail -20 "$BACKEND_LOG"
        exit 1
    fi
    sleep 5
done

# Verify backend port is listening
echo "Verifying backend port ($FASTAPI)..."
sleep 5
if ! lsof -Pi :$FASTAPI 2>/dev/null | grep -q LISTEN; then
    echo "WARNING: Backend port $FASTAPI not detected, checking for uvicorn process..."
    if ! pgrep -f "uvicorn.*:$FASTAPI" > /dev/null; then
        echo "ERROR: Backend process not found on port $FASTAPI"
        exit 1
    else
        echo "Backend process is running, continuing..."
    fi
fi

# Start frontend
echo "Starting frontend..."
cd "$CWD"
./start_frontend.sh > "$FRONTEND_LOG" 2>&1 &

# Poll frontend log for startup completion
echo "Waiting for frontend to be ready..."
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if [ -f "$FRONTEND_LOG" ]; then
        # Check for success
        if grep -q "Nginx server is ready and running!" "$FRONTEND_LOG"; then
            echo "Frontend startup complete!"
            break
        fi
        # Check for failure
        if grep -q "still could not bind\|Address already in use\|nginx:.*failed" "$FRONTEND_LOG"; then
            echo "ERROR: Frontend failed to start. Check $FRONTEND_LOG"
            tail -10 "$FRONTEND_LOG"
            exit 1
        fi
    fi
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
        echo "ERROR: Frontend failed to start within timeout"
        echo "Last lines of log:"
        tail -10 "$FRONTEND_LOG"
        exit 1
    fi
    sleep 5
done

# Verify frontend port is listening
echo "Verifying frontend ports (HTTP:$NGINX_HTTP, HTTPS:$NGINX_HTTPS)..."
sleep 5
if ! (lsof -Pi :$NGINX_HTTPS 2>/dev/null | grep -q LISTEN || lsof -Pi :$NGINX_HTTP 2>/dev/null | grep -q LISTEN); then
    echo "WARNING: Frontend ports not detected, checking nginx process..."
    if ! pgrep nginx > /dev/null; then
        echo "ERROR: Nginx process not found"
        exit 1
    else
        echo "Nginx process is running, continuing..."
    fi
fi

echo "Dispatcher startup complete at $(date)"
echo "Dispatcher services:"
echo "  Backend (FastAPI): port $FASTAPI"
lsof -Pi :$FASTAPI 2>/dev/null | grep LISTEN || echo "    (not detected)"
echo "  Frontend (nginx): ports $NGINX_HTTP/$NGINX_HTTPS"
lsof -Pi :$NGINX_HTTP 2>/dev/null | grep LISTEN || true
lsof -Pi :$NGINX_HTTPS 2>/dev/null | grep LISTEN || true
