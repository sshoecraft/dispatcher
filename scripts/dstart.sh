#!/bin/bash
# Start the dispatcher Docker container (detached).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/branding.sh"

cd "$REPO_ROOT"

# Persistent data lives in ~/.dispatcher on the host, bind-mounted to
# /opt/dispatcher in the container (see docker-compose.yml). Create it as the
# invoking user so the dir isn't auto-created root-owned by the Docker daemon.
mkdir -p "$HOME/.dispatcher"

# Run the container as us (not root) so files it writes into ~/.dispatcher stay
# owned by the caller. docker-compose.yml reads DISPATCHER_UID/GID.
export DISPATCHER_UID="$(id -u)"
export DISPATCHER_GID="$(id -g)"

echo "Starting $BRAND_APP_NAME container..."
docker compose up -d

echo
docker compose ps
