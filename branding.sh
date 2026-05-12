#!/bin/bash
#
# Source this file from any shell script to get branding env vars exported.
# Single source of truth: branding.json in this same directory. Forks override
# branding.json — they do not edit shell scripts or source code.
#
# After sourcing, the following are exported (with sensible fallbacks):
#   BRAND_SLUG            - lowercase identifier ("dispatcher" / "acm-orchestrator")
#   BRAND_APP_NAME        - display name ("Dispatcher" / "ACM Job Orchestrator")
#   BRAND_APP_SHORT_NAME  - short display name
#   PREFIX                - install prefix (defaults to $HOME/.${BRAND_SLUG})

_BRAND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_BRAND_FILE="$_BRAND_DIR/branding.json"

if [ ! -f "$_BRAND_FILE" ]; then
    echo "branding.sh: $_BRAND_FILE not found" >&2
    return 1 2>/dev/null || exit 1
fi

# Use python3 — already a hard dependency of dispatcher; avoids adding jq.
_brand_get() {
    python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], sys.argv[3]))" \
        "$_BRAND_FILE" "$1" "$2"
}

export BRAND_SLUG=$(_brand_get slug dispatcher)
export BRAND_APP_NAME=$(_brand_get appName Dispatcher)
export BRAND_APP_SHORT_NAME=$(_brand_get appShortName "$BRAND_APP_NAME")

# PREFIX defaults to /opt/dispatcher for root, ~/.dispatcher otherwise.
if [ -z "${PREFIX}" ]; then
    if [ "$(id -u)" -eq 0 ]; then
        export PREFIX="/opt/dispatcher"
    else
        export PREFIX="$HOME/.dispatcher"
    fi
fi

unset _BRAND_DIR _BRAND_FILE
unset -f _brand_get
