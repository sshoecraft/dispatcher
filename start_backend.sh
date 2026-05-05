#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/branding.sh"
backend_dir=backend

# Source port configuration
if [ -f "$PREFIX/etc/.ports" ]; then
    source "$PREFIX/etc/.ports"
fi

cd ${backend_dir} || exit 1

# Set environment variables (similar to Docker ENV)
export PYTHONUNBUFFERED=1
export PYTHONPYCACHEPREFIX="$PREFIX/tmp/__pycache__"

# Activate venv so subprocesses can find venv binaries (like dispatcher-worker)
source $PREFIX/venv/bin/activate

# Start server in background (Docker-like behavior) using python3 with timestamp logging
# Redirect all output to log file
python3 main.py > $PREFIX/logs/backend.log 2>&1 &

# Save PID for reliable shutdown
BACKEND_PID=$!
echo $BACKEND_PID > $PREFIX/tmp/backend.pid
echo "Backend started with PID: $BACKEND_PID"
echo "Logs: $PREFIX/logs/backend.log"
