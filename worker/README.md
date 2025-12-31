# Dispatcher Worker Node

HTTP REST + SSE based worker node for distributed job execution.

## Installation

```bash
# Install from wheel
pip install dispatcher-worker-2.0.0-py3-none-any.whl

# Or install from source
pip install -e .
```

## Usage

```bash
# Start worker node
dispatcher-worker --name worker1 --host 0.0.0.0 --port 8001 --backend-url https://orchestrator.example.com:8443

# Health check
dispatcher-worker --name worker1 --health-check
```

## Configuration

- `--name`: Worker name (required)
- `--host`: HTTP server bind address (default: 0.0.0.0)
- `--port`: HTTP server port (default: 8001)  
- `--backend-url`: Backend orchestrator URL (required)
- `--max-jobs`: Maximum concurrent jobs (default: 4)
- `--health-check`: Perform health check and exit

## Architecture

Worker runs an HTTP server with endpoints:
- `POST /execute` - Execute job command
- `GET /logs/{job_id}` - Stream job logs via SSE
- `GET /status` - Worker status
- `GET /health` - Health check

## Communication

- Worker registers with backend on startup
- Backend sends job execution requests via HTTP POST
- Worker streams logs back via Server-Sent Events
- Same interface works for local and remote workers