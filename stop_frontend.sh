#!/bin/bash

# Stop Frontend Server (nginx)
# This script reliably stops the frontend nginx server

# Set PREFIX with default fallback
PREFIX=${PREFIX:-${HOME}/.dispatcher}

echo "Stopping frontend server..."

frontend_dir=frontend

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load port configuration if available
if [ -f "$PREFIX/etc/.ports" ]; then
    source "$PREFIX/etc/.ports"
    echo "📋 Using configured ports: HTTP=$NGINX_HTTP, HTTPS=$NGINX_HTTPS"
else
    echo "⚠️  No port configuration found, using defaults"
    NGINX_HTTP=8081
    NGINX_HTTPS=9443
fi

# Method 1: Try graceful shutdown using nginx PID and config if available
if [ -f "$PREFIX/tmp/nginx.pid.path" ] && [ -f "$PREFIX/tmp/nginx.config.path" ]; then
    NGINX_PID=$(cat $PREFIX/tmp/nginx.pid.path 2>/dev/null)
    NGINX_CONFIG=$(cat $PREFIX/tmp/nginx.config.path 2>/dev/null)
    
    if [ ! -z "$NGINX_PID" ] && [ ! -z "$NGINX_CONFIG" ] && [ -f "$NGINX_CONFIG" ]; then
        echo "Gracefully stopping nginx with PID $NGINX_PID..."
        /usr/sbin/nginx -s quit -c $NGINX_CONFIG 2>/dev/null || true
        sleep 2
    fi
fi

# Method 2: Kill by process patterns (look for nginx with our config path)
echo "Killing nginx processes for frontend..."
pkill -f "nginx.*$PREFIX/etc/nginx.conf" 2>/dev/null || true

# Method 3: Kill processes on configured ports
echo "Killing processes on ports $NGINX_HTTP and $NGINX_HTTPS..."
PIDS_HTTP=$(lsof -Pi :$NGINX_HTTP 2>/dev/null | grep LISTEN | awk '{print $2}' | sort -u)
PIDS_HTTPS=$(lsof -Pi :$NGINX_HTTPS 2>/dev/null | grep LISTEN | awk '{print $2}' | sort -u)
if [ ! -z "$PIDS_HTTP" ]; then
    echo "Killing processes on port $NGINX_HTTP: $PIDS_HTTP"
    kill -9 $PIDS_HTTP 2>/dev/null || true
fi
if [ ! -z "$PIDS_HTTPS" ]; then
    echo "Killing processes on port $NGINX_HTTPS: $PIDS_HTTPS"
    kill -9 $PIDS_HTTPS 2>/dev/null || true
fi

# Wait for processes to terminate
sleep 2

# Method 4: Force kill any remaining nginx processes related to frontend
echo "Checking for remaining processes..."
REMAINING_NGINX=$(ps aux | grep -E "nginx.*$PREFIX/etc/nginx.conf" | grep -v grep | awk '{print $2}')

if [ ! -z "$REMAINING_NGINX" ]; then
    echo "Force killing remaining nginx processes: $REMAINING_NGINX"
    kill -9 $REMAINING_NGINX 2>/dev/null || true
fi

# Clean up temporary files
echo "Cleaning up temporary files..."
rm -f $PREFIX/tmp/nginx.pid.path 2>/dev/null || true
rm -f $PREFIX/tmp/nginx.config.path 2>/dev/null || true
rm -f $PREFIX/etc/nginx.conf 2>/dev/null || true
rm -f $PREFIX/tmp/nginx.pid 2>/dev/null || true

# SSL certificates are preserved across restarts (removed cleanup)

# Final verification
sleep 1
FINAL_CHECK_NGINX=$(ps aux | grep -E "nginx.*$PREFIX/etc/nginx.conf" | grep -v grep)
FINAL_CHECK_PORTS=$(lsof -Pi :$NGINX_HTTP 2>/dev/null | grep LISTEN; lsof -Pi :$NGINX_HTTPS 2>/dev/null | grep LISTEN)

if [ -z "$FINAL_CHECK_NGINX" ] && [ -z "$FINAL_CHECK_PORTS" ]; then
    echo "✅ All frontend processes stopped successfully"
    exit 0
else
    echo "❌ Some processes may still be running:"
    if [ ! -z "$FINAL_CHECK_NGINX" ]; then
        echo "Nginx processes:"
        echo "$FINAL_CHECK_NGINX"
    fi
    if [ ! -z "$FINAL_CHECK_PORTS" ]; then
        echo "Processes on ports $NGINX_HTTP/$NGINX_HTTPS:"
        echo "$FINAL_CHECK_PORTS"
    fi
    exit 1
fi
