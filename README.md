# Dispatcher

**Job Queue Management System**
*A modern React + FastAPI application for enterprise job orchestration and monitoring*

---

## 🚀 Overview

Dispatcher is a comprehensive job queue management system built for enterprise-grade compliance monitoring and automation. It provides real-time job monitoring, queue management, and control operations through a modern web interface.

### Key Features

- **Real-time Job Monitoring** - Live tracking of job status, progress, and logs
- **Job Queue Management** - Monitor, control, and organize background job processing  
- **Interactive Dashboard** - Modern React-based interface with real-time updates
- **Job Control Operations** - Cancel, restart, delete, and manage job lifecycle
- **Live Log Streaming** - Real-time log viewing with Server-Sent Events (SSE)
- **Enterprise Ready** - Built for high-volume job processing and monitoring

---

## 🏗️ Architecture

### Self-Contained Installation

Dispatcher uses a **PREFIX-based architecture** for flexible, self-contained installations:

- **User Installation**: `~/.dispatcher` (default)
- **System Installation**: `/opt/dispatcher`
- **Custom Location**: Any directory you choose

All components (backend, frontend, logs, data, certificates) are contained within the PREFIX directory, making it easy to manage, backup, and deploy.

### Technology Stack

#### Frontend
- **React 19** - Modern component library with latest features
- **TypeScript 5.x** - Type safety and enhanced developer experience
- **Vite 6.3** - Lightning-fast build tool and dev server
- **Tailwind CSS 4** - Utility-first styling framework
- **DaisyUI 5** - Beautiful component library built on Tailwind
- **React Router v7** - Client-side routing and navigation
- **Axios** - HTTP client for API communication
- **React Toastify** - Elegant toast notifications
- **Recharts** - Data visualization and charting

#### Backend
- **FastAPI** - High-performance Python web framework
- **SQLAlchemy** - Database ORM with async support
- **Celery** - Distributed task queue for background jobs
- **PostgreSQL/SQLite** - Database options for job storage
- **Redis** - Celery broker and result backend
- **Pydantic** - Data validation and serialization

---

## 📋 Prerequisites

- **Linux/macOS** (tested on Debian 12, RHEL/CentOS 8+, macOS)
- **Python 3.8+**
- **Node.js 16+** and npm
- **Git**
- **Redis** (for job queue)
- **nginx** (for frontend HTTPS proxy - auto-installed on Debian/Ubuntu)
- **PostgreSQL** (optional - SQLite used by default)

---

## 🚀 Installation & Setup

### 1. Run Setup Script

#### Default Installation (to ~/.dispatcher)
```bash
chmod +x setup.sh
./setup.sh
```

#### Custom Installation Location
```bash
# Install to /opt/dispatcher
PREFIX=/opt/dispatcher ./setup.sh

# Install to any custom location
PREFIX=/path/to/your/location ./setup.sh
```

The setup script will:
- Create the PREFIX directory structure
- Install Python dependencies in virtual environment
- Install Node.js packages for frontend
- Generate SSL certificates
- Create configuration files
- Build the frontend application

### 3. Start Services

```bash
# Using the default PREFIX
./start_backend.sh   # Start FastAPI backend
./start_frontend.sh  # Start frontend (nginx with HTTPS)

# Using custom PREFIX
PREFIX=/opt/dispatcher ./start_backend.sh
PREFIX=/opt/dispatcher ./start_frontend.sh
```

### 4. Access Application

The frontend will display the access URLs when it starts. Typically:
- **HTTPS**: `https://your-server:8443` (or configured port)
- **Backend API**: `http://localhost:8000`
- **API Documentation**: `http://localhost:8000/docs`

**Note**: You'll see a browser security warning for the self-signed certificate - click "Advanced" and "Proceed" to continue.

---

## 🔧 Directory Structure

The PREFIX directory contains all application files:

```
${PREFIX}/                       # Installation root (e.g., ~/.dispatcher)
├── bin/                         # Binary files (if any)
├── etc/                         # Configuration files
│   ├── .ports                   # Port configuration
│   ├── database.json           # Database settings
│   ├── config.json             # Frontend configuration
│   ├── ssl/                    # SSL certificates
│   └── nginx.conf              # Nginx configuration (generated)
├── logs/                       # Log files
│   ├── dispatcher-backend.log        # Backend logs
│   ├── nginx-access.log       # Frontend access logs
│   ├── nginx-error.log        # Frontend error logs
│   └── jobs/                  # Job-specific logs
├── data/                       # Application data
├── tmp/                        # Temporary files
│   ├── nginx.pid              # Process IDs
│   └── __pycache__/           # Python cache
└── venv/                      # Python virtual environment
```

---

## 🔧 Service Management

### Environment Variable

Set the PREFIX environment variable for convenience:

```bash
# Add to your shell profile (.bashrc, .zshrc, etc.)
export PREFIX=~/.dispatcher

# Or use a different location
export PREFIX=/opt/dispatcher
```

### Starting Services

```bash
# Start backend (FastAPI + Celery workers)
PREFIX=$PREFIX ./start_backend.sh

# Start frontend (nginx with HTTPS)
PREFIX=$PREFIX ./start_frontend.sh
```

### Stopping Services

```bash
# Stop backend services
PREFIX=$PREFIX ./stop_backend.sh

# Stop frontend service
PREFIX=$PREFIX ./stop_frontend.sh
```

### Viewing Logs

```bash
# Backend logs
tail -f $PREFIX/logs/dispatcher-backend.log

# Frontend access logs
tail -f $PREFIX/logs/nginx-access.log

# Frontend error logs  
tail -f $PREFIX/logs/nginx-error.log

# Job-specific logs
ls $PREFIX/logs/jobs/
```

### Health Checks

```bash
# Check which ports are in use
lsof -Pi | grep LISTEN

# Test backend API
curl http://localhost:$(grep FASTAPI $PREFIX/etc/.ports | cut -d= -f2)/api/jobs/

# Test frontend (will show SSL certificate warning)
curl -k https://localhost:$(grep NGINX_HTTPS $PREFIX/etc/.ports | cut -d= -f2)/
```

---

## 🛠️ Development

### Frontend Development

```bash
cd frontend
npm install              # Install dependencies
npm run dev             # Development server (port 3000)
npm run build           # Production build
npm run lint            # TypeScript + ESLint
npm run format          # Prettier formatting
```

After making frontend changes, rebuild:
```bash
cd frontend && npm run build && cd ..
```

### Backend Development

```bash
cd backend
source $PREFIX/venv/bin/activate  # Activate virtual environment
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🔧 Configuration

### Database Configuration

Edit `$PREFIX/etc/database.json` to configure database settings:

```json
{
  "database": {
    "DB_TYPE": {
      "value": "sqlite",
      "description": "Database type (sqlite, postgresql, mysql)"
    },
    "PG_HOST": {
      "value": "localhost",
      "description": "PostgreSQL host"
    }
  }
}
```

### Frontend Configuration

Edit `$PREFIX/etc/config.json` for frontend settings:

```json
{
  "API_URL": "https://localhost:8443"
}
```

### Port Configuration

The system automatically detects available ports and creates `$PREFIX/etc/.ports`:

```bash
export NGINX_HTTP=8080
export NGINX_HTTPS=8443
export FASTAPI=8000
```

To use different ports, edit this file or run:
```bash
PREFIX=$PREFIX ./port_manager.sh force
```

---

## 🚦 API Endpoints

### Job Management
- `GET /api/jobs/` - List jobs with pagination and filtering
- `POST /api/jobs/{job_id}/cancel` - Cancel running job
- `POST /api/jobs/{job_id}/retry` - Restart failed job  
- `DELETE /api/jobs/{job_id}` - Delete job entry
- `GET /api/jobs/{job_id}/logs` - Get job logs
- `GET /api/jobs/{job_id}/logs/realtime` - Stream live logs (SSE)

### Job Creation
- `POST /api/jobs/run` - Run a job by name
- `POST /api/jobs/create/demo-task` - Create demo job
- `POST /api/jobs/create/actt` - Create ACTT job

For complete API documentation, visit `/docs` when the backend is running.

---

## 📋 Job Queue System

### Running Jobs

Use the `run_job` script to submit jobs:

```bash
# Basic job execution
./run_job "my-job-name"

# Job with arguments
./run_job "data-import" '{"database": "production"}'

# Job with custom creator
./run_job "backup-job" '{"retention": 30}' --created-by "admin"

# Using custom PREFIX
PREFIX=/opt/dispatcher./run_job "my-job"
```

### Job States
- **PENDING** - Job queued, waiting to start
- **RUNNING** - Job currently executing  
- **SUCCESS** - Job completed successfully
- **FAILURE** - Job failed with errors
- **REVOKED** - Job was cancelled

### Job Operations
- **Monitor** - Real-time status and progress tracking
- **Cancel** - Stop running jobs gracefully
- **Restart** - Retry failed jobs with same parameters
- **Delete** - Remove job entries from queue
- **Logs** - View execution logs with real-time streaming

---

## 🚀 Deployment

### Multiple Installation Example

You can run multiple instances with different PREFIXes:

```bash
# Development instance
PREFIX=~/.dispatcher-dev ./setup.sh
PREFIX=~/.dispatcher-dev ./start_backend.sh
PREFIX=~/.dispatcher-dev ./start_frontend.sh

# Production instance  
PREFIX=/opt/dispatcher-prod ./setup.sh
PREFIX=/opt/dispatcher-prod ./start_backend.sh
PREFIX=/opt/dispatcher-prod ./start_frontend.sh
```

### Production Considerations
- Replace self-signed certificates with valid SSL certificates in `$PREFIX/etc/ssl/`
- Configure proper database connection in `$PREFIX/etc/database.json`
- Set up Redis clustering for high availability
- Implement proper authentication
- Configure monitoring and alerting
- Use a process manager like systemd or supervisor for production deployments
- Set appropriate file permissions for `$PREFIX` directory

### Systemd Service (Auto-start on Boot)

For production deployments, you can configure the system to automatically start on boot using systemd.

#### Installation

1. **Create the dispatcher system user:**
```bash
# Create system user (no login shell, no home directory)
sudo useradd --system --no-create-home --shell /usr/sbin/nologin dispatcher
```

2. **Install to /opt/dispatcher:**
```bash
# Create and set ownership
sudo mkdir -p /opt/dispatcher
sudo chown dispatcher:dispatcher /opt/dispatcher

# Run setup as dispatcher user
sudo -u dispatcher PREFIX=/opt/dispatcher ./setup.sh
```

3. **Copy the service file:**
```bash
sudo cp dispatcher.service /etc/systemd/system/
```

4. **Reload systemd and enable the service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable dispatcher.service
```

5. **Start the service:**
```bash
sudo systemctl start dispatcher.service
```

#### Service Management

```bash
# Check service status
sudo systemctl status dispatcher.service

# Start service
sudo systemctl start dispatcher.service

# Stop service
sudo systemctl stop dispatcher.service

# Restart service
sudo systemctl restart dispatcher.service

# View service logs
journalctl -u dispatcher.service -f

# Disable auto-start on boot
sudo systemctl disable dispatcher.service
```

**Note:** The systemd service uses `startup.sh` and `shutdown.sh` scripts which handle sequential startup with health checks and graceful shutdown of both backend and frontend services.

---

## 🔄 Maintenance

### Backup

```bash
# Backup entire installation
tar -czf dispatcher-backup-$(date +%Y%m%d).tar.gz $PREFIX

# Backup just configuration and data
tar -czf dispatcher-config-backup-$(date +%Y%m%d).tar.gz $PREFIX/etc $PREFIX/data $PREFIX/logs
```

### Updates

```bash
# Pull latest code
git pull origin main

# Reinstall dependencies and rebuild
PREFIX=$PREFIX ./setup.sh

# Restart services
PREFIX=$PREFIX ./stop_backend.sh
PREFIX=$PREFIX ./stop_frontend.sh
PREFIX=$PREFIX ./start_backend.sh
PREFIX=$PREFIX ./start_frontend.sh
```

### Uninstall

```bash
# Stop services
PREFIX=$PREFIX ./stop_backend.sh
PREFIX=$PREFIX ./stop_frontend.sh

# Remove installation
PREFIX=$PREFIX ./setup.sh --uninstall
```

---

## 🆘 Troubleshooting

### Common Issues

1. **Port conflicts**: Run `PREFIX=$PREFIX ./port_manager.sh show` to check port status
2. **Permission errors**: Ensure user has write access to PREFIX directory
3. **SSL certificate warnings**: Expected with self-signed certificates
4. **Database connection**: Check `$PREFIX/etc/database.json` configuration
5. **Service not starting**: Check logs in `$PREFIX/logs/`

### Log Locations

All logs are stored in `$PREFIX/logs/`:
- Backend: `dispatcher-backend.log`
- Frontend access: `nginx-access.log`
- Frontend errors: `nginx-error.log`
- Job logs: `jobs/` directory

---

## 🤝 Contributing

1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/amazing-feature`
3. **Make changes** and test thoroughly
4. **Commit changes**: `git commit -m 'Add amazing feature'`
5. **Push to branch**: `git push origin feature/amazing-feature`
6. **Open Pull Request**

### Development Guidelines
- Follow TypeScript strict mode
- Use Prettier for code formatting
- Write descriptive commit messages
- Test changes before committing
- Update documentation for new features
- Test with different PREFIX locations

---

## 🆘 Support

For technical support or questions:
- Create an issue in this repository
- Review the logs for troubleshooting information