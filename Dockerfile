FROM node:20-slim AS frontend

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
COPY branding.json /branding.json
# Build default (non-portd) version
RUN npm run build -- --outDir /build/dist


FROM python:3.11-slim

# Install system dependencies including nodejs for portd rebuild
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    redis-server \
    curl \
    lsof \
    procps \
    gcc \
    libpq-dev \
    openssl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create directories (app files in /app, persistent data in /opt/dispatcher)
RUN mkdir -p /app/{tmp,www} /opt/dispatcher/{etc,logs,data,lib} /opt/dispatcher/logs/jobs

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Build and install worker
COPY worker/ ./worker/
RUN pip install --no-cache-dir ./worker/

# Copy backend
COPY backend/ ./backend/

# Copy built frontend (default build for non-portd mode)
COPY --from=frontend /build/dist ./www/

# Copy frontend source and node_modules for portd rebuild
COPY --from=frontend /build ./frontend-src/

# Copy branding config (both locations for compatibility)
COPY branding.json ./etc/
COPY branding.json ./

# Copy entrypoint
COPY scripts/docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENV PREFIX=/opt/dispatcher
ENV PYTHONUNBUFFERED=1

# Allow running the container as an arbitrary (non-root) host uid:gid so files
# written into the /opt/dispatcher bind mount are owned by the calling user, not
# root. Give npm a writable cache/home, drop the stale build-stage tsc cache, and
# make the dirs written at runtime (nginx pid + pycache in /app/tmp, and the
# portd-mode SPA rebuild in /app/www) writable by any uid.
ENV HOME=/tmp \
    npm_config_cache=/tmp/.npm
RUN mkdir -p /app/tmp /app/www /var/lib/nginx /var/log/nginx \
    && rm -rf /app/frontend-src/node_modules/.tmp \
              /app/frontend-src/node_modules/.vite \
              /app/frontend-src/node_modules/.vite-temp \
              /app/frontend-src/node_modules/.cache \
    && chmod -R 0777 /app/tmp /app/www /var/lib/nginx /var/log/nginx \
    && chmod 0777 /app/frontend-src/node_modules

EXPOSE 8080

ENTRYPOINT ["/app/docker-entrypoint.sh"]
