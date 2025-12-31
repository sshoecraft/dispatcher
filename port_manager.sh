#!/bin/bash

# Port Manager - Detects available ports and manages port configuration
# Creates .ports file with consistent port assignments

# Set PREFIX with default fallback
PREFIX=${PREFIX:-${HOME}/.dispatcher}

PORTS_FILE=".ports"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORTS_PATH="${PREFIX}/etc/${PORTS_FILE}"

# Frontend port sets (nginx)
DEFAULT_FRONTEND_PORTS=(
    "NGINX_HTTP=80"
    "NGINX_HTTPS=443"
)

ALTERNATE_FRONTEND_PORTS=(
    "NGINX_HTTP=8080"
    "NGINX_HTTPS=8443"
)

FALLBACK_FRONTEND_PORTS=(
    "NGINX_HTTP=9080"
    "NGINX_HTTPS=9443"
)

# Backend port (FastAPI) - will auto-increment if needed
DEFAULT_BACKEND_PORT=8000

# Function to check if a port is in use
is_port_in_use() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1
    else
        netstat -ln 2>/dev/null | grep ":$port " >/dev/null 2>&1
    fi
}

# Function to extract port number from "NAME=PORT" format
extract_port() {
    echo "$1" | cut -d'=' -f2
}

# Function to check if any port in a set is in use
check_port_set() {
    # Check bash version for nameref support
    if [[ ${BASH_VERSION%%.*} -ge 4 ]]; then
        local -n port_set=$1
        for port_def in "${port_set[@]}"; do
            local port=$(extract_port "$port_def")
            if is_port_in_use "$port"; then
                return 1  # Port in use
            fi
        done
    else
        # Bash 3 compatible version using eval
        eval "local port_array=(\"\${${1}[@]}\")"
        for port_def in "${port_array[@]}"; do
            local port=$(extract_port "$port_def")
            if is_port_in_use "$port"; then
                return 1  # Port in use
            fi
        done
    fi
    return 0  # All ports available
}

# Function to find next available backend port starting from a base port
find_available_backend_port() {
    local start_port=$1
    local port=$start_port
    
    while is_port_in_use "$port"; do
        ((port++))
        if [[ $port -gt 9999 ]]; then
            echo "❌ Error: No available ports found in range $start_port-9999"
            return 1
        fi
    done
    
    echo $port
    return 0
}

# Function to write ports to file
write_ports_file() {
    local backend_port=$2
    
    # Ensure PREFIX/etc directory exists
    mkdir -p "$(dirname "$PORTS_PATH")"
    
    echo "# Dispatcher Port Configuration" > "$PORTS_PATH"
    echo "# Generated on $(date)" >> "$PORTS_PATH"
    echo "# PREFIX: $PREFIX" >> "$PORTS_PATH"
    echo "" >> "$PORTS_PATH"
    
    # Write frontend ports
    if [[ ${BASH_VERSION%%.*} -ge 4 ]]; then
        local -n frontend_ports=$1
        for port_def in "${frontend_ports[@]}"; do
            echo "export $port_def" >> "$PORTS_PATH"
        done
    else
        # Bash 3 compatible version using eval
        eval "local port_array=(\"\${${1}[@]}\")"
        for port_def in "${port_array[@]}"; do
            echo "export $port_def" >> "$PORTS_PATH"
        done
    fi
    
    # Write backend port
    echo "export FASTAPI=$backend_port" >> "$PORTS_PATH"
    
    echo "" >> "$PORTS_PATH"
    echo "# Source this file to load port variables:" >> "$PORTS_PATH"
    echo "# source .ports" >> "$PORTS_PATH"
    
    chmod +x "$PORTS_PATH"
}

# Function to load ports from file
load_ports() {
    if [[ -f "$PORTS_PATH" ]]; then
        source "$PORTS_PATH"
        return 0
    else
        return 1
    fi
}

# Function to detect and assign ports
detect_and_assign_ports() {
    echo "🔍 Detecting available ports..."
    
    local selected_frontend_ports
    local selected_backend_port
    
    # Check frontend ports based on user privileges
    if [[ $EUID -eq 0 ]]; then
        echo "🔑 Running as root, can use privileged ports"
        # Try default frontend ports first
        if check_port_set DEFAULT_FRONTEND_PORTS; then
            echo "✅ Default frontend ports (80/443) available"
            selected_frontend_ports=DEFAULT_FRONTEND_PORTS
        elif check_port_set ALTERNATE_FRONTEND_PORTS; then
            echo "⚠️  Default frontend ports in use, using alternates (8080/8443)"
            selected_frontend_ports=ALTERNATE_FRONTEND_PORTS
        elif check_port_set FALLBACK_FRONTEND_PORTS; then
            echo "⚠️  Alternate frontend ports in use, using fallbacks (9080/9443)"
            selected_frontend_ports=FALLBACK_FRONTEND_PORTS
        else
            echo "❌ All frontend port sets are in use!"
            return 1
        fi
    else
        echo "👤 Running as non-root user, skipping privileged ports (80/443)"
        # Try alternate frontend ports first for non-root
        if check_port_set ALTERNATE_FRONTEND_PORTS; then
            echo "✅ Alternate frontend ports (8080/8443) available"
            selected_frontend_ports=ALTERNATE_FRONTEND_PORTS
        elif check_port_set FALLBACK_FRONTEND_PORTS; then
            echo "⚠️  Alternate frontend ports in use, using fallbacks (9080/9443)"
            selected_frontend_ports=FALLBACK_FRONTEND_PORTS
        else
            echo "❌ All non-privileged frontend port sets are in use!"
            return 1
        fi
    fi
    
    # Find available backend port (auto-increment from default)
    echo "🔍 Finding available backend port..."
    selected_backend_port=$(find_available_backend_port $DEFAULT_BACKEND_PORT)
    if [[ $? -ne 0 ]]; then
        echo "❌ Could not find available backend port"
        return 1
    fi
    
    if [[ $selected_backend_port -eq $DEFAULT_BACKEND_PORT ]]; then
        echo "✅ Backend port $selected_backend_port available"
    else
        echo "⚠️  Backend port $DEFAULT_BACKEND_PORT in use, using $selected_backend_port instead"
    fi
    
    # Write configuration
    echo ""
    echo "📋 Final port assignment:"
    if [[ ${BASH_VERSION%%.*} -ge 4 ]]; then
        local -n final_frontend_ports=$selected_frontend_ports
        for port_def in "${final_frontend_ports[@]}"; do
            echo "   - $port_def"
        done
    else
        # Bash 3 compatible version using eval
        eval "local port_array=(\"\${${selected_frontend_ports}[@]}\")"
        for port_def in "${port_array[@]}"; do
            echo "   - $port_def"
        done
    fi
    echo "   - FASTAPI=$selected_backend_port"
    
    write_ports_file $selected_frontend_ports $selected_backend_port
    return 0
}

# Function to show current port configuration
show_ports() {
    if [[ -f "$PORTS_PATH" ]]; then
        echo "📋 Current port configuration:"
        echo ""
        grep "^export" "$PORTS_PATH" | sed 's/export /   /' | while IFS='=' read -r name port; do
            local status="🔴 Not listening"
            if is_port_in_use "$port"; then
                status="🟢 Listening"
            fi
            printf "   %-12s = %-5s %s\n" "$name" "$port" "$status"
        done
    else
        echo "📋 No port configuration file found (.ports)"
        echo "Run 'initialize' to detect and create port configuration."
    fi
}

# Function to initialize ports (only if .ports doesn't exist)
initialize_ports() {
    if [[ -f "$PORTS_PATH" ]]; then
        echo "📋 Port configuration already exists:"
        show_ports
        return 0
    else
        detect_and_assign_ports
    fi
}

# Function to force re-detect ports
force_detect_ports() {
    if [[ -f "$PORTS_PATH" ]]; then
        echo "🗑️  Removing existing port configuration..."
        rm "$PORTS_PATH"
    fi
    detect_and_assign_ports
}

# Main command processing
case "${1:-}" in
    "initialize"|"init")
        initialize_ports
        ;;
    "show"|"status")
        show_ports
        ;;
    "detect"|"force")
        force_detect_ports
        ;;
    "load")
        if load_ports; then
            echo "✅ Port configuration loaded"
        else
            echo "❌ No port configuration file found"
            exit 1
        fi
        ;;
    "help"|"-h"|"--help"|*)
        echo "Port Manager - Dispatcher Port Detection and Management"
        echo ""
        echo "Usage: [PREFIX=/path/to/install] $0 <command>"
        echo ""
        echo "Environment Variables:"
        echo "  PREFIX            - Installation prefix (default: \$HOME/.dispatcher)"
        echo ""
        echo "Commands:"
        echo "  initialize, init  - Initialize port configuration (only if .ports doesn't exist)"
        echo "  show, status      - Show current port configuration and status"
        echo "  detect, force     - Force re-detect and reassign ports"
        echo "  load              - Load port configuration into environment"
        echo "  help              - Show this help message"
        echo ""
        echo "Port Sets:"
        echo "  Default:   HTTP=80, HTTPS=443, FastAPI=8000"
        echo "  Alternate: HTTP=8080, HTTPS=8443, FastAPI=8001"
        echo "  Fallback:  HTTP=9080, HTTPS=9443, FastAPI=8002"
        echo ""
        echo "Current PREFIX: $PREFIX"
        echo "Ports file: $PORTS_PATH"
        ;;
esac
