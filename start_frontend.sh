#!/bin/bash

# start_frontend.sh - Start the frontend server (nginx).
# Branding (app name, prefix, etc.) is sourced from branding.json.
#
# Two modes, picked automatically based on whether portd is running on :2019:
#
#   portd mode   - portd allocates an HTTP port, frontend registers as
#                  $PORTD_FRONTEND_NAME (default $BRAND_SLUG), reachable at
#                  http://<host>/$PORTD_FRONTEND_NAME/. The SPA is built with
#                  vite --base=/$PORTD_FRONTEND_NAME/ so its asset URLs match
#                  the path. nginx serves the built files only — no API
#                  proxying — and the SPA hits portd directly via API_URL.
#
#                  Caveat: dispatcher's SPA hardcodes absolute /api/... paths
#                  in many places (lib/auth.ts, pages/*) instead of prefixing
#                  with API_URL. Until that's fixed, those calls won't reach
#                  the backend through portd. portd-mode startup itself works,
#                  but the app won't be fully functional without SPA changes.
#
#   direct mode  - portd not running. Existing behavior: nginx serves
#                  HTTP on $NGINX_HTTP and HTTPS on $NGINX_HTTPS with a
#                  self-signed cert, and proxies /api/, /docs, etc. directly
#                  to the FastAPI backend on $FASTAPI.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/branding.sh"

# Check setup completed
PORTS_FILE="$PREFIX/etc/.ports"
if [ ! -f "$PORTS_FILE" ]; then
    echo "❌ Error: Setup not completed!"
    echo ""
    echo "Please run setup.sh first to initialize the system:"
    echo "  ./setup.sh"
    exit 1
fi

echo "✅ Setup verified: Found port configuration"

frontend_dir=frontend

echo "🚀 Starting $BRAND_APP_NAME Frontend Server"
echo "=================================="

# Load port configuration (created by setup.sh)
source "$PORTS_FILE"
echo "📋 Direct-mode ports: HTTP=$NGINX_HTTP, HTTPS=$NGINX_HTTPS, FastAPI=$FASTAPI"

# State files
NGINX_CONFIG="$PREFIX/etc/nginx.conf"
NGINX_PID_PATH_FILE="$PREFIX/tmp/nginx.pid.path"
NGINX_CONFIG_PATH_FILE="$PREFIX/tmp/nginx.config.path"
NGINX_PORT_FILE="$PREFIX/tmp/nginx.port"
PORTD_NAME_FILE="$PREFIX/tmp/nginx.portd-name"

# portd integration
PORTD_ADMIN="${PORTD_ADMIN:-http://localhost:2019}"
PORTD_FRONTEND_NAME="${PORTD_FRONTEND_NAME:-$BRAND_SLUG}"
PORTD_BACKEND_NAME="${PORTD_BACKEND_NAME:-${BRAND_SLUG}-backend}"
USE_PORTD=false
if curl -sf -o /dev/null "$PORTD_ADMIN/portd/services" 2>/dev/null; then
    USE_PORTD=true
fi

cd "$SCRIPT_DIR/${frontend_dir}"
echo "📁 Frontend directory: $(pwd)"

if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found in ${frontend_dir} directory."
    exit 1
fi

# Auto-detect nginx binary
NGINX_BIN=""
for nginx_path in "/usr/sbin/nginx" "/usr/bin/nginx" "/usr/local/sbin/nginx" "/usr/local/bin/nginx" "/opt/homebrew/bin/nginx"; do
    if [ -x "$nginx_path" ]; then
        NGINX_BIN="$nginx_path"
        break
    fi
done
if [ -z "$NGINX_BIN" ] && command -v nginx &> /dev/null; then
    NGINX_BIN=$(command -v nginx)
fi
if [ -z "$NGINX_BIN" ]; then
    echo "❌ Error: nginx not found. Install nginx first."
    exit 1
fi

# Auto-detect nginx prefix (for mime.types)
NGINX_PREFIX=$($NGINX_BIN -t 2>&1 | grep "configuration file" | head -1 | sed 's/.*configuration file \(.*\)nginx.conf.*/\1/' | sed 's/\/$//')
if [ -z "$NGINX_PREFIX" ]; then
    for prefix in "/opt/homebrew/etc/nginx" "/usr/local/etc/nginx" "/etc/nginx"; do
        if [ -f "$prefix/mime.types" ]; then
            NGINX_PREFIX="$prefix"
            break
        fi
    done
fi
if [ -z "$NGINX_PREFIX" ] || [ ! -f "$NGINX_PREFIX/mime.types" ]; then
    echo "❌ Error: nginx mime.types not found. Check nginx installation."
    exit 1
fi

# Verify deps installed by setup.sh
if [ ! -d "node_modules" ]; then
    echo "❌ Error: Node.js dependencies not found! Run setup.sh first."
    exit 1
fi

# SSL certs (only used in direct mode but cheap to verify)
SSL_DIR="$PREFIX/etc/ssl"
if [ "$USE_PORTD" != "true" ]; then
    if [ ! -f "$SSL_DIR/cert.pem" ] || [ ! -f "$SSL_DIR/key.pem" ]; then
        echo "❌ Error: SSL certificates not found in $SSL_DIR"
        echo "   Run setup.sh first."
        exit 1
    fi
fi

# Use cert hostname (matches self-signed CN) for direct-mode display
SERVER_IP="localhost"

# ===========================================================================
# Mode-specific setup: allocate port, choose API_URL and base path
# ===========================================================================
if [ "$USE_PORTD" = "true" ]; then
    echo "🛰  portd detected at $PORTD_ADMIN — allocating port for \"$PORTD_FRONTEND_NAME\""
    ALLOC_PAYLOAD=$(printf '{"name":"%s"}' "$PORTD_FRONTEND_NAME")
    ALLOC_RESP=$(curl -sf -X POST "$PORTD_ADMIN/portd/allocate" \
        -H "Content-Type: application/json" -d "$ALLOC_PAYLOAD" 2>/dev/null || true)
    if [ -z "$ALLOC_RESP" ]; then
        echo "❌ Error: portd /portd/allocate request failed"
        exit 1
    fi
    NGINX_PORT=$(echo "$ALLOC_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['port'])" 2>/dev/null || true)
    if [ -z "$NGINX_PORT" ]; then
        echo "❌ Error: could not parse port from portd response: $ALLOC_RESP"
        exit 1
    fi
    echo "🎯 portd allocated port $NGINX_PORT for \"$PORTD_FRONTEND_NAME\""
    BASE_PATH="/$PORTD_FRONTEND_NAME/"
    API_URL="/$PORTD_BACKEND_NAME"
    PUBLIC_URL="http://$SERVER_IP/$PORTD_FRONTEND_NAME/"
else
    if [ "${USE_LOCALHOST:-false}" = "true" ]; then
        API_URL="https://localhost:$NGINX_HTTPS"
        echo "🔒 Using localhost API URL for SSH tunnel compatibility"
    else
        API_URL="https://$SERVER_IP:$NGINX_HTTPS"
        echo "🌐 Using server IP API URL for direct access"
    fi
    BASE_PATH="/"
    PUBLIC_URL="https://$SERVER_IP:$NGINX_HTTPS"
fi
echo "🔧 API_URL = $API_URL"

# ===========================================================================
# Build the SPA
# ===========================================================================
echo "🔨 Building production bundle to $PREFIX/www (base=$BASE_PATH)..."
if [ "$BASE_PATH" = "/" ]; then
    npm run build -- --outDir "$PREFIX/www" --emptyOutDir
else
    npm run build -- --outDir "$PREFIX/www" --emptyOutDir --base="$BASE_PATH"
fi

if [ ! -d "$PREFIX/www" ]; then
    echo "❌ Error: Build failed — $PREFIX/www directory not found"
    exit 1
fi

# Inject runtime API_URL into the built config.json (overwrites the placeholder
# from branding.json). The dispatcher-branding vite plugin writes config.json
# during build.
WWW_CONFIG="$PREFIX/www/config.json"
if [ ! -f "$WWW_CONFIG" ]; then
    echo "❌ Error: Build did not produce $WWW_CONFIG"
    exit 1
fi
if command -v jq &> /dev/null; then
    jq --arg url "$API_URL" '.API_URL = $url' "$WWW_CONFIG" > "$WWW_CONFIG.tmp" && mv "$WWW_CONFIG.tmp" "$WWW_CONFIG"
else
    sed -i.bak "s|\"API_URL\":[[:space:]]*\"[^\"]*\"|\"API_URL\": \"$API_URL\"|" "$WWW_CONFIG"
    rm -f "${WWW_CONFIG}.bak"
fi
echo "✅ Build completed successfully"

# ===========================================================================
# Generate nginx config + start
# ===========================================================================
if [ "$USE_PORTD" = "true" ]; then
    # portd mode: HTTP only on the allocated port. portd strips the
    # /$PORTD_FRONTEND_NAME/ prefix before forwarding (default behavior),
    # so nginx serves at root. The SPA's vite --base of /$PORTD_FRONTEND_NAME/
    # makes asset URLs match the public-facing path. No API proxying — the
    # SPA hits portd directly via API_URL.
    cat > "$NGINX_CONFIG" << EOF
worker_processes 1;
error_log $PREFIX/logs/nginx-error.log;
pid $PREFIX/tmp/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include $NGINX_PREFIX/mime.types;
    default_type application/octet-stream;

    access_log $PREFIX/logs/nginx-access.log;

    sendfile on;
    keepalive_timeout 65;

    server {
        listen 0.0.0.0:$NGINX_PORT;
        server_name _;

        location / {
            root $PREFIX/www;
            index index.html;
            try_files \$uri \$uri/ /index.html;
        }

        error_page 500 502 503 504 /50x.html;
        location = /50x.html {
            root $PREFIX/www;
        }
    }
}
EOF
else
    # Direct mode: HTTP redirect + HTTPS server with API proxying.
    cat > "$NGINX_CONFIG" << EOF
worker_processes 1;
error_log $PREFIX/logs/nginx-error.log;
pid $PREFIX/tmp/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include $NGINX_PREFIX/mime.types;
    default_type application/octet-stream;

    access_log $PREFIX/logs/nginx-access.log;

    sendfile on;
    keepalive_timeout 65;

    # HTTP -> HTTPS redirect
    server {
        listen 0.0.0.0:$NGINX_HTTP;
        server_name _;
        return 301 https://\$host:$NGINX_HTTPS\$request_uri;
    }

    # HTTPS server
    server {
        listen 0.0.0.0:$NGINX_HTTPS ssl;
        server_name _;

        ssl_certificate $SSL_DIR/cert.pem;
        ssl_certificate_key $SSL_DIR/key.pem;

        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        # SSE jobs realtime
        location ~ ^/api/jobs/realtime\$ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 3600s;
            proxy_connect_timeout 60s;
            proxy_send_timeout 3600s;
            proxy_set_header Connection '';
            proxy_http_version 1.1;
            chunked_transfer_encoding off;
            add_header X-Accel-Buffering no;
        }

        location ~ ^/api/jobs/.*/logs/realtime\$ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 3600s;
            proxy_connect_timeout 60s;
            proxy_send_timeout 3600s;
            proxy_set_header Connection '';
            proxy_http_version 1.1;
            chunked_transfer_encoding off;
            add_header X-Accel-Buffering no;
        }

        # SSE log stream endpoints (jobs/workers/queues)
        location ~ ^/api/(jobs|workers|queues)/.*/logs/stream\$ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 3600s;
            proxy_connect_timeout 60s;
            proxy_send_timeout 3600s;
            proxy_set_header Connection '';
            proxy_http_version 1.1;
            chunked_transfer_encoding off;
            add_header X-Accel-Buffering no;
        }

        # Non-streaming log endpoints
        location ~ ^/api/jobs/.*/logs\$ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_buffering off;
            proxy_cache off;
            proxy_max_temp_file_size 0;
        }

        location /docs {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }

        location /redoc {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }

        location /openapi.json {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }

        location /api/ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }

        location / {
            root $PREFIX/www;
            index index.html;
            try_files \$uri \$uri/ /index.html;
        }

        error_page 500 502 503 504 /50x.html;
        location = /50x.html {
            root $PREFIX/www;
        }
    }
}
EOF
fi

# Stop any prior nginx using this config
pkill -f "nginx.*$NGINX_CONFIG" 2>/dev/null || true
sleep 1

if [ "$USE_PORTD" = "true" ]; then
    echo "🌐 Starting nginx (HTTP on port $NGINX_PORT, registered as \"$PORTD_FRONTEND_NAME\")..."
else
    echo "🌐 Starting nginx (HTTP $NGINX_HTTP -> HTTPS $NGINX_HTTPS)..."
fi
$NGINX_BIN -c "$NGINX_CONFIG"

NGINX_PID=$(cat "$PREFIX/tmp/nginx.pid")
echo "$NGINX_PID" > "$NGINX_PID_PATH_FILE"
echo "$NGINX_CONFIG" > "$NGINX_CONFIG_PATH_FILE"

# State files for stop_frontend.sh
if [ "$USE_PORTD" = "true" ]; then
    echo "$NGINX_PORT" > "$NGINX_PORT_FILE"
    echo "$PORTD_FRONTEND_NAME" > "$PORTD_NAME_FILE"
else
    rm -f "$NGINX_PORT_FILE" "$PORTD_NAME_FILE" 2>/dev/null || true
fi

echo ""
echo "✅ $BRAND_APP_NAME Frontend started"
echo "   - URL:       $PUBLIC_URL"
echo "   - Doc root:  $PREFIX/www"
echo "   - Nginx PID: $NGINX_PID"
echo "   - Config:    $NGINX_CONFIG"
echo "   - Logs:      $PREFIX/logs/nginx-{access,error}.log"
if [ "$USE_PORTD" = "true" ]; then
    echo "   - portd:     registered as \"$PORTD_FRONTEND_NAME\" on port $NGINX_PORT"
fi
echo ""
echo "🛑 Stop with: $SCRIPT_DIR/stop_frontend.sh"
if [ "$USE_PORTD" != "true" ]; then
    echo "⚠️  Browser will warn about the self-signed cert — proceed past it."
fi

# Health check
sleep 2
if [ "$USE_PORTD" = "true" ]; then
    HEALTH_URL="http://localhost:$NGINX_PORT/"
else
    HEALTH_URL="https://localhost:$NGINX_HTTPS"
fi
if curl -sk "$HEALTH_URL" > /dev/null; then
    echo "✅ Server health check passed"
else
    echo "❌ Server health check failed"
    $NGINX_BIN -s quit -c "$NGINX_CONFIG" 2>/dev/null || true
    exit 1
fi
