#!/bin/bash
# Shutdown script for Dispatcher
# Stops frontend first, then backend

set -e

# Get the directory where this script is located (the repo directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CWD="$SCRIPT_DIR"

# Set PREFIX - expand ~ to actual home directory
export PREFIX="${PREFIX:-$HOME/.dispatcher}"

# Ensure PATH includes common locations for tools
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

echo "Stopping Dispatcher at $(date)"

# Stop frontend first
echo "Stopping frontend..."
cd "$CWD"
./stop_frontend.sh

# Wait a moment for frontend to fully stop
sleep 2

# Stop backend
echo "Stopping backend..."
cd "$CWD"
./stop_backend.sh

# Verify all processes stopped
sleep 2
echo "Verifying all processes stopped..."
if lsof -Pi | grep LISTEN | grep -E "(python3|nginx)"; then
    echo "WARNING: Some processes still running"
else
    echo "All services stopped successfully"
fi

echo "Dispatcher shutdown complete at $(date)"
