#!/bin/bash
# Stop the dispatcher Docker container.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/branding.sh"

cd "$REPO_ROOT"

echo "Stopping $BRAND_APP_NAME container..."
docker compose down
