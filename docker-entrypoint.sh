#!/bin/bash
set -e

PREFIX=/opt/dispatcher
APP_DIR=/app
PORTD_BACKEND_NAME="${PORTD_BACKEND_NAME:-dispatcher-backend}"
PORTD_FRONTEND_NAME="${PORTD_FRONTEND_NAME:-dispatcher}"

# Detect portd
PORTD_ADMIN="${PORTD_ADMIN:-http://localhost:2019}"
USE_PORTD=false
if curl -sf -o /dev/null "$PORTD_ADMIN/portd/services" 2>/dev/null; then
    USE_PORTD=true
    echo "portd detected at $PORTD_ADMIN"
fi

# Allocate ports from portd or use defaults
if [ "$USE_PORTD" = "true" ]; then
    # Allocate backend port
    echo "Requesting port allocation for backend..."
    ALLOC_RESP=$(curl -sf -X POST "$PORTD_ADMIN/portd/allocate" \
        -H "Content-Type: application/json" -d "{\"name\":\"$PORTD_BACKEND_NAME\"}" 2>/dev/null || true)
    if [ -z "$ALLOC_RESP" ]; then
        echo "Error: portd backend allocation failed"
        exit 1
    fi
    BACKEND_PORT=$(echo "$ALLOC_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['port'])" 2>/dev/null || true)
    echo "portd allocated backend port $BACKEND_PORT as \"$PORTD_BACKEND_NAME\""
    export UVICORN_ROOT_PATH="/$PORTD_BACKEND_NAME"

    # Allocate frontend port
    echo "Requesting port allocation for frontend..."
    ALLOC_RESP=$(curl -sf -X POST "$PORTD_ADMIN/portd/allocate" \
        -H "Content-Type: application/json" -d "{\"name\":\"$PORTD_FRONTEND_NAME\"}" 2>/dev/null || true)
    if [ -z "$ALLOC_RESP" ]; then
        echo "Error: portd frontend allocation failed"
        exit 1
    fi
    NGINX_PORT=$(echo "$ALLOC_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['port'])" 2>/dev/null || true)
    echo "portd allocated frontend port $NGINX_PORT as \"$PORTD_FRONTEND_NAME\""

    # Set API_URL for portd routing
    API_URL="/$PORTD_BACKEND_NAME"
else
    BACKEND_PORT="${BACKEND_PORT:-8000}"
    NGINX_PORT="${NGINX_PORT:-8080}"
fi

# Ensure directories exist
mkdir -p "$PREFIX/etc" "$PREFIX/logs" "$PREFIX/data" "$PREFIX/lib" "$PREFIX/logs/jobs" "$APP_DIR/tmp"

# Use existing Redis password or generate one
if [ -f "$PREFIX/etc/.redis_password" ]; then
    REDIS_PASSWORD=$(cat "$PREFIX/etc/.redis_password")
else
    REDIS_PASSWORD=$(openssl rand -base64 32)
    echo "$REDIS_PASSWORD" > "$PREFIX/etc/.redis_password"
    chmod 600 "$PREFIX/etc/.redis_password"
fi

# Start Redis on port 6378 (avoids conflict with system Redis on 6379)
echo "Starting Redis on port 6378..."
redis-server --daemonize yes --port 6378 --bind 0.0.0.0 --requirepass "$REDIS_PASSWORD" --dir "$PREFIX/data"
sleep 1

# Generate nginx config
cat > "$PREFIX/etc/nginx.conf" << EOF
worker_processes auto;
error_log $PREFIX/logs/nginx-error.log;
pid $APP_DIR/tmp/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    access_log $PREFIX/logs/nginx-access.log;
    sendfile on;
    keepalive_timeout 65;

    server {
        listen 0.0.0.0:$NGINX_PORT;
        server_name _;

        location ~ ^/api/(jobs|workers|queues)/.*/logs/(realtime|stream)\$ {
            proxy_pass http://127.0.0.1:$BACKEND_PORT;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 3600s;
            proxy_http_version 1.1;
            chunked_transfer_encoding off;
        }

        location ~ ^/api/jobs/realtime\$ {
            proxy_pass http://127.0.0.1:$BACKEND_PORT;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 3600s;
            proxy_http_version 1.1;
            chunked_transfer_encoding off;
        }

        location /api/ {
            proxy_pass http://127.0.0.1:$BACKEND_PORT;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
        }

        location /docs {
            proxy_pass http://127.0.0.1:$BACKEND_PORT;
        }

        location /redoc {
            proxy_pass http://127.0.0.1:$BACKEND_PORT;
        }

        location /openapi.json {
            proxy_pass http://127.0.0.1:$BACKEND_PORT;
        }

        location / {
            root $APP_DIR/www;
            index index.html;
            try_files \$uri \$uri/ /index.html;
        }
    }
}
EOF

# For portd mode, rebuild frontend with correct base path
if [ "$USE_PORTD" = "true" ]; then
    echo "Rebuilding frontend for portd base path /$PORTD_FRONTEND_NAME/..."
    cd "$APP_DIR/frontend-src"
    npm run build -- --outDir "$APP_DIR/www" --emptyOutDir --base="/$PORTD_FRONTEND_NAME/"
    cd "$APP_DIR"
fi

# Inject API_URL into config.json
if [ -n "$API_URL" ] && [ -f "$APP_DIR/www/config.json" ]; then
    echo "Setting API_URL to $API_URL"
    sed -i "s|\"API_URL\":[[:space:]]*\"[^\"]*\"|\"API_URL\": \"$API_URL\"|" "$APP_DIR/www/config.json"
fi

# Start nginx
echo "Starting nginx on port $NGINX_PORT..."
nginx -c "$PREFIX/etc/nginx.conf"

# Start backend
echo "Starting backend on port $BACKEND_PORT..."
cd "$APP_DIR/backend"
export PYTHONPYCACHEPREFIX="$APP_DIR/tmp/__pycache__"
exec python3 main.py "$BACKEND_PORT"
