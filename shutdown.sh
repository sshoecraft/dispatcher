#!/bin/bash
# Stop frontend first, then backend.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/branding.sh"

echo "Stopping $BRAND_APP_NAME at $(date)"

"$SCRIPT_DIR/stop_frontend.sh"
"$SCRIPT_DIR/stop_backend.sh"

echo "$BRAND_APP_NAME shutdown complete at $(date)"
