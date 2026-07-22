#!/bin/bash

# Stop frontend nginx server.
# Reads state files written by start_frontend.sh to know what to clean up:
#   $PREFIX/tmp/nginx.port         - allocated port (portd mode)
#   $PREFIX/tmp/nginx.portd-name   - portd service name (portd mode)
#   $PREFIX/tmp/nginx.pid.path     - graceful shutdown PID
#   $PREFIX/tmp/nginx.config.path  - graceful shutdown config path
# Falls back to .ports HTTP/HTTPS cleanup when no state files exist.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/branding.sh"

echo "🛑 Stopping $BRAND_APP_NAME frontend..."

NGINX_CONFIG_FILE="$PREFIX/etc/nginx.conf"
NGINX_PID_PATH_FILE="$PREFIX/tmp/nginx.pid.path"
NGINX_CONFIG_PATH_FILE="$PREFIX/tmp/nginx.config.path"
NGINX_PORT_FILE="$PREFIX/tmp/nginx.port"
PORTD_NAME_FILE="$PREFIX/tmp/nginx.portd-name"
PORTD_ADMIN="${PORTD_ADMIN:-http://localhost:2019}"

# Resolve which ports might be in use: portd-allocated (from state file)
# or direct-mode HTTP/HTTPS from .ports.
PORTS_TO_CHECK=()
if [ -f "$NGINX_PORT_FILE" ]; then
    PORTS_TO_CHECK+=("$(cat "$NGINX_PORT_FILE" 2>/dev/null)")
elif [ -f "$PREFIX/etc/.ports" ]; then
    source "$PREFIX/etc/.ports"
    PORTS_TO_CHECK+=("$NGINX_HTTP" "$NGINX_HTTPS")
else
    PORTS_TO_CHECK+=("8081" "9443")
fi

echo "📋 Ports: ${PORTS_TO_CHECK[*]}"

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

# Find an nginx binary for graceful shutdown
NGINX_BIN=""
for nginx_path in "/usr/sbin/nginx" "/usr/bin/nginx" "/usr/local/sbin/nginx" "/usr/local/bin/nginx" "/opt/homebrew/bin/nginx"; do
    if [ -x "$nginx_path" ]; then
        NGINX_BIN="$nginx_path"
        break
    fi
done
[ -z "$NGINX_BIN" ] && command -v nginx &> /dev/null && NGINX_BIN=$(command -v nginx)

# Method 1: Graceful shutdown via saved PID + config path
if [ -f "$NGINX_PID_PATH_FILE" ] && [ -f "$NGINX_CONFIG_PATH_FILE" ]; then
    NGINX_PID=$(cat "$NGINX_PID_PATH_FILE" 2>/dev/null)
    NGINX_CONFIG=$(cat "$NGINX_CONFIG_PATH_FILE" 2>/dev/null)
    if [ -n "$NGINX_PID" ] && [ -n "$NGINX_CONFIG" ] && [ -f "$NGINX_CONFIG" ] && [ -n "$NGINX_BIN" ]; then
        echo "Gracefully stopping nginx (PID $NGINX_PID)..."
        "$NGINX_BIN" -s quit -c "$NGINX_CONFIG" 2>/dev/null || true
        sleep 2
    fi
fi

# Method 2: Kill by config-path pattern
echo "Killing nginx processes referencing $NGINX_CONFIG_FILE..."
pkill -f "nginx.*$NGINX_CONFIG_FILE" 2>/dev/null || true

# Method 3: Kill anything on configured ports
for port in "${PORTS_TO_CHECK[@]}"; do
    [ -z "$port" ] && continue
    PIDS=$(lsof -Pi :"$port" 2>/dev/null | grep LISTEN | awk '{print $2}' | sort -u)
    if [ -n "$PIDS" ]; then
        echo "Killing processes on port $port: $PIDS"
        kill -9 $PIDS 2>/dev/null || true
    fi
done

sleep 2

# Method 4: Force kill stragglers
REMAINING=$(ps aux | grep -E "nginx.*$NGINX_CONFIG_FILE" | grep -v grep | awk '{print $2}')
if [ -n "$REMAINING" ]; then
    echo "Force killing remaining nginx: $REMAINING"
    kill -9 $REMAINING 2>/dev/null || true
fi

# Cleanup state files (SSL certs in $PREFIX/etc/ssl preserved across restarts)
echo "Cleaning up state files..."
rm -f "$NGINX_PID_PATH_FILE" "$NGINX_CONFIG_PATH_FILE" "$NGINX_CONFIG_FILE" \
      "$NGINX_PORT_FILE" "$PORTD_NAME_FILE" "$PREFIX/tmp/nginx.pid" 2>/dev/null || true

# Final verification
sleep 1
FINAL_NGINX=$(ps aux | grep -E "nginx.*$NGINX_CONFIG_FILE" | grep -v grep)
FINAL_PORTS=""
for port in "${PORTS_TO_CHECK[@]}"; do
    [ -z "$port" ] && continue
    res=$(lsof -Pi :"$port" 2>/dev/null | grep LISTEN)
    [ -n "$res" ] && FINAL_PORTS="$FINAL_PORTS$res
"
done

if [ -z "$FINAL_NGINX" ] && [ -z "$FINAL_PORTS" ]; then
    echo "✅ Frontend stopped successfully"
    exit 0
else
    echo "❌ Some processes may still be running:"
    [ -n "$FINAL_NGINX" ] && { echo "  nginx:"; echo "$FINAL_NGINX"; }
    [ -n "$FINAL_PORTS" ] && { echo "  ports:"; echo "$FINAL_PORTS"; }
    exit 1
fi
