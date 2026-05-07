#!/bin/bash
# Start backend, then frontend. Aborts if backend fails.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/branding.sh"

echo "Starting $BRAND_APP_NAME at $(date)"

"$SCRIPT_DIR/start_backend.sh"
"$SCRIPT_DIR/start_frontend.sh"

echo "$BRAND_APP_NAME startup complete at $(date)"
