#!/bin/bash

# start_frontend.sh - Start the Dispatcher frontend server
# Production-like setup with nginx proxy and SSL

set -e

# Set PREFIX with default fallback
PREFIX=${PREFIX:-${HOME}/.dispatcher}

# Check if setup has been completed by verifying .ports file exists
PORTS_FILE="$PREFIX/etc/.ports"
if [ ! -f "$PORTS_FILE" ]; then
    echo "❌ Error: Setup not completed!"
    echo ""
    echo "Please run setup.sh first to initialize the system:"
    echo "  ./setup.sh"
    echo ""
    echo "Setup will create:"
    echo "  - Directory structure under $PREFIX"
    echo "  - Node.js dependencies (npm install)"
    echo "  - SSL certificates"
    echo "  - Port configuration (.ports file)"
    exit 1
fi

echo "✅ Setup verified: Found port configuration"

frontend_dir=frontend

echo "🚀 Starting Dispatcher Frontend Server"
echo "=================================="

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load port configuration (created by setup.sh)
if ! source "$PREFIX/etc/.ports" 2>/dev/null; then
    echo "❌ Error: Port configuration not found!"
    echo "Please run setup.sh first to create port configuration at: $PREFIX/etc/.ports"
    exit 1
fi

echo "📋 Using ports: HTTP=$NGINX_HTTP, HTTPS=$NGINX_HTTPS, FastAPI=$FASTAPI"

# Change to the ${frontend_dir} directory
cd "$SCRIPT_DIR/${frontend_dir}"

echo "📁 Changed to directory: $(pwd)"

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found in ${frontend_dir} directory."
    exit 1
fi

# Auto-detect nginx binary and config locations
NGINX_BIN=""
# Try common locations for nginx binary
for nginx_path in "/usr/sbin/nginx" "/usr/bin/nginx" "/usr/local/sbin/nginx" "/usr/local/bin/nginx"; do
    if [ -x "$nginx_path" ]; then
        NGINX_BIN="$nginx_path"
        break
    fi
done
# Fallback to PATH if available
if [ -z "$NGINX_BIN" ] && command -v nginx &> /dev/null; then
    NGINX_BIN=$(command -v nginx)
fi

if [ -z "$NGINX_BIN" ]; then
    echo "❌ Error: nginx is not installed or not found in common locations. Please install nginx first."
    exit 1
fi

# Auto-detect nginx prefix (where config files are located)
NGINX_PREFIX=$($NGINX_BIN -t 2>&1 | grep "configuration file" | head -1 | sed 's/.*configuration file \(.*\)nginx.conf.*/\1/' | sed 's/\/$//')
if [ -z "$NGINX_PREFIX" ]; then
    # Fallback: try common locations
    for prefix in "/opt/homebrew/etc/nginx" "/usr/local/etc/nginx" "/etc/nginx"; do
        if [ -f "$prefix/mime.types" ]; then
            NGINX_PREFIX="$prefix"
            break
        fi
    done
fi

if [ -z "$NGINX_PREFIX" ] || [ ! -f "$NGINX_PREFIX/mime.types" ]; then
    echo "❌ Error: Could not find nginx mime.types file. Please check nginx installation."
    exit 1
fi

# Use full path if nginx not in PATH
if ! command -v nginx &> /dev/null; then
    alias nginx="$NGINX_BIN"
fi

# Verify dependencies exist (installed by setup.sh)
if [ ! -d "node_modules" ]; then
    echo "❌ Error: Node.js dependencies not found!"
    echo "Please run setup.sh first to install npm packages."
    exit 1
fi

# Use certificate hostname instead of IP to avoid SSL certificate errors
# Override with certificate hostname that matches the SSL cert
SERVER_IP="localhost"
echo "🔐 Using certificate hostname: $SERVER_IP"

# Check if SSL certificates exist (should be created by setup.sh)
SSL_DIR="$PREFIX/etc/ssl"
if [ ! -f "$SSL_DIR/cert.pem" ] || [ ! -f "$SSL_DIR/key.pem" ]; then
    echo "❌ Error: SSL certificates not found in $SSL_DIR"
    echo "   Run setup.sh first to create SSL certificates and directory structure"
    exit 1
fi

# Create local config by copying original and updating API_URL
echo "🔧 Creating local config for nginx proxy setup..."

# Create config in PREFIX/etc and symlink to public
CONFIG_FILE="$PREFIX/etc/config.json"
if [ -f "public/config.json" ] && [ ! -f "$CONFIG_FILE" ]; then
    # Copy the original config.json to PREFIX location
    cp public/config.json "$CONFIG_FILE"
    echo "📋 Config copied to $CONFIG_FILE"
fi

# Always ensure symlink exists
if [ ! -L "public/config.local.json" ]; then
    ln -sf "$CONFIG_FILE" public/config.local.json
    echo "🔗 Created symlink: public/config.local.json -> $CONFIG_FILE"
fi

# Check if original config exists for API_URL update
if [ -f "public/config.json" ]; then
    # Check if we should use localhost (likely SSH tunnel) or server IP
    # Use localhost for SSH tunnel compatibility, server IP for direct access
    if [ "${USE_LOCALHOST:-false}" = "true" ]; then
        API_URL="https://localhost:$NGINX_HTTPS"
        echo "🔒 Using localhost API URL for SSH tunnel compatibility"
    else
        API_URL="https://$SERVER_IP:$NGINX_HTTPS"
        echo "🌐 Using server IP API URL for direct access"
    fi
    
    # Update only the API_URL in the PREFIX config file using jq
    if command -v jq &> /dev/null; then
        jq --arg url "$API_URL" '.API_URL = $url' public/config.json > "$CONFIG_FILE"
    else
        # Fallback if jq is not available - use sed
        cp public/config.json "$CONFIG_FILE"
        sed -i.bak "s|\"API_URL\":[[:space:]]*\"[^\"]*\"|\"API_URL\": \"$API_URL\"|" "$CONFIG_FILE"
        rm -f "${CONFIG_FILE}.bak"
    fi
else
    echo "❌ Error: public/config.json not found"
    exit 1
fi

# Copy the config for build process
cp public/config.local.json public/config.json

# Build the production version directly to $PREFIX/www
echo "🔨 Building production build to $PREFIX/www..."
npm run build -- --outDir "$PREFIX/www" --emptyOutDir

# Restore original config to avoid committing changes
git checkout -- public/config.json 2>/dev/null || true

# Check if build was successful
if [ ! -d "$PREFIX/www" ]; then
    echo "❌ Error: Build failed - $PREFIX/www directory not found"
    exit 1
fi

# Copy the config.local.json to www/config.json for runtime
cp public/config.local.json "$PREFIX/www/config.json"

echo "✅ Build completed successfully"

# Kill any existing server on the configured ports
#echo "🧹 Cleaning up existing servers on ports $NGINX_HTTP and $NGINX_HTTPS..."
#lsof -ti:$NGINX_HTTP | xargs kill -9 2>/dev/null || true
#lsof -ti:$NGINX_HTTPS | xargs kill -9 2>/dev/null || true

# Stop any existing nginx processes we might have started
#pkill -f "nginx.*${frontend_dir}" 2>/dev/null || true

# Create a custom nginx config for this instance
NGINX_CONFIG="$PREFIX/etc/nginx.conf"
CURRENT_DIR=$(pwd)

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
    
    # HTTP server to redirect to HTTPS
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
        
        # SSL configuration
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;
        
        # Special handling for SSE endpoints
        location ~ ^/api/jobs/realtime$ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            
            # SSE-specific settings
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
        
        location ~ ^/api/jobs/.*/logs/realtime$ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            
            # SSE-specific settings
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
        
        # SSE streaming endpoints for all log streams
        location ~ ^/api/(jobs|workers|queues)/.*/logs/stream$ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            
            # SSE-specific settings
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
        
        # Special handling for log endpoints (non-streaming)
        location ~ ^/api/jobs/.*/logs$ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            
            # Disable caching and buffering for large log files
            proxy_buffering off;
            proxy_cache off;
            proxy_max_temp_file_size 0;
        }
        
        # Proxy FastAPI docs endpoints to backend
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
        
        # Proxy API calls to FastAPI backend
        location /api/ {
            proxy_pass http://127.0.0.1:$FASTAPI;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }
        
        # Serve React app
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

echo "🌐 Starting nginx server with HTTPS on port $NGINX_HTTPS..."
echo "📍 Server will be available at: https://$SERVER_IP:$NGINX_HTTPS"
echo "🔐 SSL Certificate: Self-signed (browser will show security warning)"

# Start nginx with our custom config
$NGINX_BIN -c $NGINX_CONFIG

# Get the nginx PID
NGINX_PID=$(cat "$PREFIX/tmp/nginx.pid")

# Store the PID and config path for cleanup
echo $NGINX_PID > "$PREFIX/tmp/nginx.pid.path"
echo "$NGINX_CONFIG" > "$PREFIX/tmp/nginx.config.path"

echo ""
echo "✅ Dispatcher Server started successfully with nginx!"
echo "🔐 Access your application at: https://$SERVER_IP:$NGINX_HTTPS"
echo "⚠️  Note: You'll see a browser security warning - click 'Advanced' and 'Proceed to localhost'"
echo "🔧 Nginx PID: $NGINX_PID"
echo "📄 Config: $NGINX_CONFIG"
echo "🛑 To stop the server, run: $NGINX_BIN -s quit -c $NGINX_CONFIG"
echo ""
echo "📋 Server Details:"
echo "   - HTTPS Port: $NGINX_HTTPS (with SSL/TLS)"
echo "   - HTTP Port: $NGINX_HTTP (redirects to HTTPS)"
echo "   - Document Root: $PREFIX/www"
echo "   - SSL Certificate: $SSL_DIR/cert.pem"
echo "   - SSL Key: $SSL_DIR/key.pem"
echo "   - SPA Routing: Enabled (try_files fallback)"
echo "   - Nginx Config: $NGINX_CONFIG"
echo "   - PREFIX: $PREFIX"
echo "   - Access Log: $PREFIX/logs/nginx-access.log"
echo "   - Error Log: $PREFIX/logs/nginx-error.log"

# Wait a moment and test if server started
sleep 2
if curl -sk https://localhost:$NGINX_HTTPS > /dev/null; then
    echo "✅ Server health check passed"
else
    echo "❌ Server health check failed"
    $NGINX_BIN -s quit -c $NGINX_CONFIG 2>/dev/null || true
    exit 1
fi

echo ""
echo "🎉 Nginx server is ready and running!"
echo "💡 This setup exactly matches the Docker container behavior"
echo "🔄 HTTP traffic on port $NGINX_HTTP will redirect to HTTPS on port $NGINX_HTTPS"
