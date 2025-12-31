#!/bin/bash

# Dispatcher Setup Script
# This script installs all necessary dependencies and configures the system
# Usage: PREFIX=/path/to/install ./setup.sh [--uninstall]

set -e  # Exit on any error

# Set PREFIX with default fallback
PREFIX=${PREFIX:-${HOME}/.dispatcher}

UNINSTALL=false

# Parse command line arguments
for arg in "$@"; do
    case $arg in
        --uninstall)
        UNINSTALL=true
        shift
        ;;
        --help|-h)
        cat << EOF
Dispatcher Setup Script

Usage: [PREFIX=/path/to/install] $0 [OPTIONS]

Environment Variables:
  PREFIX            Installation prefix (default: \$HOME/.dispatcher)
                    Examples:
                    - PREFIX=~/.dispatcher (user installation)
                    - PREFIX=/opt/dispatcher (system installation)

Options:
  --uninstall       Remove Dispatcher installation
  --help, -h        Show this help message

Examples:
  $0                              # Install to ~/.dispatcher
  PREFIX=/opt/dispatcher $0      # Install to /opt/dispatcher
  $0 --uninstall                 # Remove installation
EOF
        exit 0
        ;;
        *)
        echo "Unknown option: $arg"
        exit 1
        ;;
    esac
done

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
print_status() {
    echo -e "${GREEN}[+]${NC} $1"
}

print_error() {
    echo -e "${RED}[!]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[*]${NC} $1"
}

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Uninstall function
uninstall_dispatcher() {
    print_warning "Uninstalling Dispatcher from PREFIX: $PREFIX"

    # Stop any running processes
    print_status "Stopping any running Dispatcher processes..."
    ./stop_backend.sh 2>/dev/null || true
    ./stop_frontend.sh 2>/dev/null || true
    
    # Remove PREFIX directory
    if [[ -d "$PREFIX" ]]; then
        read -p "Remove installation directory $PREFIX? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$PREFIX"
            print_status "Installation directory removed"
        fi
    fi
    
    print_status "Uninstallation complete!"
    exit 0
}

# Function to create database.json configuration
create_database_config() {
    print_status "Creating database configuration..."
    
    mkdir -p "$PREFIX/etc"
    
    cat > "$PREFIX/etc/database.json" << 'EOF'
{
  "database": {
    "DB_TYPE": {
      "value": "sqlite",
      "is_sensitive": false,
      "description": "Database type (sqlite, postgresql, mysql)",
      "default_value": "sqlite",
      "is_required": true,
      "validation_pattern": "^(sqlite|postgresql|mysql)$"
    },
    "PG_HOST": {
      "value": "localhost",
      "is_sensitive": false,
      "description": "PostgreSQL host",
      "default_value": "localhost",
      "is_required": false,
      "validation_pattern": null
    },
    "PG_DB": {
      "value": "orchestrator",
      "is_sensitive": false,
      "description": "PostgreSQL database name",
      "default_value": "orchestrator",
      "is_required": false,
      "validation_pattern": null
    },
    "PG_PORT": {
      "value": "5432",
      "is_sensitive": false,
      "description": "PostgreSQL port",
      "default_value": "5432",
      "is_required": false,
      "validation_pattern": "^[0-9]+$"
    },
    "PG_USER": {
      "value": "",
      "is_sensitive": false,
      "description": "PostgreSQL username",
      "default_value": "",
      "is_required": false,
      "validation_pattern": null
    },
    "PG_PWD": {
      "value": "",
      "is_sensitive": true,
      "description": "PostgreSQL password",
      "default_value": "",
      "is_required": false,
      "validation_pattern": null
    },
    "PG_MANAGED_IDENTITY_USER": {
      "value": "dispatcher-dev",
      "is_sensitive": false,
      "description": "Azure managed identity user",
      "default_value": "dispatcher-dev",
      "is_required": false,
      "validation_pattern": null
    },
    "USE_MANAGED_IDENTITY": {
      "value": "false",
      "is_sensitive": false,
      "description": "Use Azure managed identity authentication",
      "default_value": "false",
      "is_required": false,
      "validation_pattern": "^(true|false)$"
    }
  }
}
EOF
    
    print_status "Database configuration created at $PREFIX/etc/database.json"
}

# Function to create frontend config.json
create_frontend_config() {
    print_status "Creating frontend configuration..."
    
    # Load port configuration to set API_URL
    if [[ -f "$PREFIX/etc/.ports" ]]; then
        source "$PREFIX/etc/.ports"
    else
        NGINX_HTTPS=8443  # fallback
    fi
    
    cat > "$PREFIX/etc/config.json" << EOF
{
  "API_URL": "https://localhost:$NGINX_HTTPS"
}
EOF
    
    print_status "Frontend configuration created at $PREFIX/etc/config.json"
}

# Handle uninstall
if [[ "$UNINSTALL" == true ]]; then
    uninstall_dispatcher
fi

# =============================================================================
# Prerequisite Check
# =============================================================================
# Check all required dependencies upfront before doing anything.
# If anything is missing, report it and exit. We do NOT install packages.

print_status "Checking prerequisites..."

MISSING_COMMANDS=()
MISSING_PACKAGES=()

# Check for required commands and track what's missing
check_command() {
    local cmd="$1"
    local package="$2"
    if ! command -v "$cmd" &> /dev/null; then
        MISSING_COMMANDS+=("$cmd")
        MISSING_PACKAGES+=("$package")
    fi
}

# Check basic required commands
check_command "python3" "python3"
check_command "node" "nodejs"
check_command "npm" "npm"
check_command "openssl" "openssl"
check_command "redis-server" "redis-server"
check_command "lsof" "lsof"

# Check nginx (can be in various locations)
NGINX_FOUND=false
for nginx_path in "/usr/sbin/nginx" "/usr/bin/nginx" "/usr/local/sbin/nginx" "/usr/local/bin/nginx"; do
    if [ -x "$nginx_path" ]; then
        NGINX_FOUND=true
        break
    fi
done
if [ "$NGINX_FOUND" = false ] && ! command -v nginx &> /dev/null; then
    MISSING_COMMANDS+=("nginx")
    MISSING_PACKAGES+=("nginx")
fi

# Check Python version (only if python3 exists)
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
    PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')

    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
        print_error "Python 3.8 or higher is required. Found: Python $PYTHON_VERSION"
        exit 1
    fi

    # Check for venv module (requires python3-venv package on Debian/Ubuntu)
    # We check for ensurepip because venv imports fine but fails without it
    if ! python3 -c "import ensurepip" &> /dev/null; then
        MISSING_COMMANDS+=("python3 venv module")
        MISSING_PACKAGES+=("python3-venv")
    fi
fi

# If anything is missing, report and exit
if [ ${#MISSING_COMMANDS[@]} -gt 0 ]; then
    print_error "Missing required dependencies:"
    echo
    for i in "${!MISSING_COMMANDS[@]}"; do
        echo "  - ${MISSING_COMMANDS[$i]}"
    done
    echo
    print_warning "Please install the following packages before running this script:"
    echo
    # Deduplicate packages
    printf '%s\n' "${MISSING_PACKAGES[@]}" | sort -u | while read -r pkg; do
        echo "  $pkg"
    done
    echo
    echo "On Debian/Ubuntu, you can install them with:"
    echo "  sudo apt-get install $(printf '%s ' "${MISSING_PACKAGES[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' ')"
    echo
    exit 1
fi

# All prerequisites met - report what we found
print_status "Python $PYTHON_VERSION found"
NODE_VERSION=$(node -v | cut -d'v' -f2)
print_status "Node.js v$NODE_VERSION found"
print_status "All prerequisites satisfied"

# Check if system Redis is running (Dispatcher runs its own Redis instance)
if systemctl is-active --quiet redis-server 2>/dev/null || systemctl is-active --quiet redis 2>/dev/null; then
    print_error "System Redis server is running!"
    echo
    echo "Dispatcher runs its own Redis instance and will conflict with the system service."
    echo "Please stop and disable the system Redis server before continuing:"
    echo
    echo "  sudo systemctl stop redis-server"
    echo "  sudo systemctl disable redis-server"
    echo
    exit 1
fi
print_status "System Redis not running (OK)"

# Installation begins here
print_status "Installing Dispatcher with PREFIX: $PREFIX"

# Create directory structure
print_status "Creating directory structure..."
mkdir -p "$PREFIX"/{bin,etc,logs,data,tmp,venv,lib}
mkdir -p "$PREFIX/etc/ssl"
mkdir -p "$PREFIX/logs/jobs"

# Create virtual environment (always recreate for clean state)
print_status "Creating Python virtual environment..."
if [[ -d "$PREFIX/venv" ]]; then
    print_status "Removing existing virtual environment..."
    rm -rf "$PREFIX/venv"
fi
python3 -m venv "$PREFIX/venv"
print_status "Created new Python virtual environment at $PREFIX/venv"

# Install Python dependencies
print_status "Installing Python dependencies..."
"$PREFIX/venv/bin/pip" install --upgrade pip
"$PREFIX/venv/bin/pip" install -r backend/requirements.txt

# Build and install worker package
print_status "Building worker wheel..."
mkdir -p worker/dist
"$PREFIX/venv/bin/pip" wheel worker/ -w worker/dist/ --no-deps
WORKER_WHEEL=$(ls -t worker/dist/*.whl | head -1)
print_status "Installing worker package from $WORKER_WHEEL..."
"$PREFIX/venv/bin/pip" install "$WORKER_WHEEL"

# Verify critical Python dependencies actually work
print_status "Verifying Python dependencies..."
if ! "$PREFIX/venv/bin/python3" -c "
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
pwd_context.hash('test')
" 2>/dev/null; then
    print_error "Password hashing verification failed!"
    print_error "This is usually a bcrypt/passlib compatibility issue."
    print_error "Try: $PREFIX/venv/bin/pip install 'bcrypt>=4.0.0,<4.1.0'"
    exit 1
fi
print_status "Password hashing: OK"

if ! "$PREFIX/venv/bin/python3" -c "
from jose import jwt
jwt.encode({'test': 'data'}, 'secret', algorithm='HS256')
" 2>/dev/null; then
    print_error "JWT token verification failed!"
    print_error "Check python-jose installation."
    exit 1
fi
print_status "JWT tokens: OK"

if ! "$PREFIX/venv/bin/python3" -c "
from sqlalchemy import create_engine
" 2>/dev/null; then
    print_error "SQLAlchemy verification failed!"
    exit 1
fi
print_status "Database (SQLAlchemy): OK"

# Generate Redis password for backend
print_status "Generating Redis password..."
REDIS_PASSWORD=$(openssl rand -base64 32)
echo "$REDIS_PASSWORD" > "$PREFIX/etc/.redis_password"
chmod 600 "$PREFIX/etc/.redis_password"
print_status "Redis password generated and saved to $PREFIX/etc/.redis_password"

# Install frontend dependencies
print_status "Installing frontend dependencies..."
cd frontend
npm install
cd ..

# Initialize port configuration
print_status "Initializing port configuration..."
PREFIX="$PREFIX" ./port_manager.sh initialize

if [[ ! -f "$PREFIX/etc/.ports" ]]; then
    print_error "Failed to generate port configuration"
    exit 1
fi

# Create database configuration
create_database_config

# Create frontend configuration
create_frontend_config

# Create SSL certificates
print_status "Creating SSL certificates..."
SSL_DIR="$PREFIX/etc/ssl"
if [[ ! -f "$SSL_DIR/cert.pem" ]] || [[ ! -f "$SSL_DIR/key.pem" ]]; then
    print_status "Creating self-signed SSL certificate..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$SSL_DIR/key.pem" \
        -out "$SSL_DIR/cert.pem" \
        -subj "/C=US/ST=State/L=City/O=Dispatcher/CN=localhost"
    print_status "SSL certificates created in $SSL_DIR/"
else
    print_status "SSL certificates already exist"
fi

print_status "Setup complete!"
echo
print_warning "============================================"
print_warning "Installation Complete"
print_warning "============================================"
echo "Installation PREFIX: $PREFIX"
echo
echo "Directory structure created:"
echo "  - $PREFIX/bin/        # Binary files (if any)"
echo "  - $PREFIX/etc/        # Configuration files"
echo "  - $PREFIX/logs/       # Log files"
echo "  - $PREFIX/data/       # Application data"
echo "  - $PREFIX/tmp/        # Temporary files"
echo "  - $PREFIX/venv/       # Python virtual environment"
echo "  - $PREFIX/etc/ssl/    # SSL certificates"
echo
echo "Configuration files:"
echo "  - $PREFIX/etc/.ports         # Port configuration"
echo "  - $PREFIX/etc/database.json  # Database settings"
echo "  - $PREFIX/etc/config.json    # Frontend settings"
echo
print_warning "Next steps:"
echo "1. Start backend:    PREFIX=$PREFIX ./start_backend.sh"
echo "2. Start frontend:   PREFIX=$PREFIX ./start_frontend.sh"
echo "3. Access web UI:    Check frontend startup output for URL"
echo
echo "To uninstall: PREFIX=$PREFIX $0 --uninstall"
echo
echo "All scripts will honor the PREFIX environment variable."
echo "Set PREFIX=$PREFIX in your shell for convenience:"
echo "  export PREFIX=$PREFIX"
echo
print_status "Setup complete!"