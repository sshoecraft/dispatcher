#!/usr/bin/env python3
"""
Worker Node HTTP Server
Executes commands and streams output back to backend logger service
"""

import asyncio
import subprocess
import sys
import os
import pty
import json
import httpx
from typing import Dict, Optional, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel, Field
import uvicorn
from threading import Lock
from pathlib import Path
from .output import output
from .redis_logger import RedisLogger


class ExecuteRequest(BaseModel):
    """Request to execute a command"""
    execution_id: str = Field(..., description="Execution ID")
    command: str = Field(..., description="Base64 encoded command to execute")
    args: list = Field(default_factory=list, description="Base64 encoded arguments")


class ExecuteResponse(BaseModel):
    """Response from command execution"""
    execution_id: str = Field(..., description="Execution ID")
    pid: int = Field(..., description="Process ID")
    status: str = Field(..., description="Execution status")


class StatusResponse(BaseModel):
    """Process status response"""
    execution_id: str = Field(..., description="Execution ID")
    status: str = Field(..., description="Process status: running, completed, failed")
    exit_code: Optional[int] = Field(None, description="Exit code if completed")
    pid: Optional[int] = Field(None, description="Process ID")


class HealthResponse(BaseModel):
    """Worker health response"""
    status: str = Field(..., description="Worker status")
    running_jobs: int = Field(..., description="Number of running jobs")
    max_jobs: int = Field(..., description="Maximum concurrent jobs")


class ConfigRequest(BaseModel):
    """Worker configuration update request"""
    max_jobs: int = Field(..., description="Maximum concurrent jobs", ge=1, le=1000)


class ConfigResponse(BaseModel):
    """Worker configuration response"""
    max_jobs: int = Field(..., description="Current maximum concurrent jobs")


class WorkerNode:
    def __init__(self, backend_url: str, worker_name: str, max_jobs: int = 10):
        self.backend_url = backend_url.rstrip('/')
        self.worker_name = worker_name
        self.max_jobs = max_jobs
        self.running_processes: Dict[str, subprocess.Popen] = {}
        self.job_status: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        
        # Redis logger for high-throughput log streaming
        self._redis_logger = RedisLogger(backend_url)
        self._redis_connected = False
    
    def get_worker_id(self) -> int:
        """Extract worker ID from worker name for callbacks"""
        # Assuming worker names follow pattern like "worker1", "worker-2", etc.
        import re
        match = re.search(r'\d+', self.worker_name)
        return int(match.group()) if match else 1
    
    async def execute_command(self, request: ExecuteRequest) -> ExecuteResponse:
        """Execute command and start streaming output to backend"""
        import base64
        
        execution_id = request.execution_id
        
        with self._lock:
            if len(self.running_processes) >= self.max_jobs:
                raise HTTPException(status_code=429, detail="Maximum concurrent jobs reached")
            
            if execution_id in self.running_processes:
                raise HTTPException(status_code=409, detail=f"Execution {execution_id} already running")
        
        try:
            # Decode base64 command
            command = base64.b64decode(request.command).decode('utf-8')
            
            # Decode base64 arguments
            args = []
            for arg_b64 in request.args:
                args.append(base64.b64decode(arg_b64).decode('utf-8'))
            
            # Build command line as list to avoid shell interpretation corrupting JSON
            # Use shlex.split to properly handle quoted arguments (e.g., bash -c "...")
            import shlex
            command_parts = shlex.split(command)
            cmd_list = command_parts + args
            
            # Log the execution start
            output.info(f"Executing job {execution_id}: {' '.join(cmd_list)}")
            
            # Use pty to force unbuffered output (pseudo-terminal tricks programs into thinking they're interactive)
            master_fd, slave_fd = pty.openpty()
            
            process = subprocess.Popen(
                cmd_list,
                shell=False,
                stdout=slave_fd,
                stderr=slave_fd,
                stdin=subprocess.DEVNULL,
                preexec_fn=os.setsid  # Create new session to avoid terminal interference
            )
            
            # Close slave end since we only need the master
            os.close(slave_fd)
            
            # Set master fd to non-blocking mode
            import fcntl
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            with self._lock:
                self.running_processes[execution_id] = process
                self.job_status[execution_id] = {
                    "status": "running",
                    "pid": process.pid,
                    "exit_code": None
                }
            
            # Notify backend that job started
            await self._notify_backend(execution_id, "started", pid=process.pid)
            
            # Start output streaming task with pty master fd
            output.info(f"DEBUG: Starting output streaming task for {execution_id}")
            asyncio.create_task(self._stream_output_to_backend(execution_id, process, master_fd))
            
            return ExecuteResponse(
                execution_id=execution_id,
                pid=process.pid,
                status="started"
            )
            
        except Exception as e:
            # Notify backend of failure
            await self._notify_backend(execution_id, "failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to start command: {e}")
    
    async def _stream_output_to_backend(self, execution_id: str, process: subprocess.Popen, master_fd: int):
        """Stream process output to backend logger service in real-time using pty"""
        output.info(f"DEBUG: _stream_output_to_backend started for {execution_id}")
        # Debug messages removed for clean operation - add --debug flag to worker to enable
        
        try:
            # Stream output from pty master fd for true real-time output
            line_buffer = bytearray()
            bytes_read_total = 0
            lines_sent = 0
            
            while process.poll() is None:  # While process is running
                try:
                    # Read available bytes from pty (non-blocking)
                    byte_data = os.read(master_fd, 1024)
                    if byte_data:
                        bytes_read_total += len(byte_data)
                        print(f"[STREAM] Read {len(byte_data)} bytes from PTY (total: {bytes_read_total})", flush=True)
                        
                        # Process each byte for line detection
                        for byte in byte_data:
                            line_buffer.append(byte)
                            
                            # Check for newline (line complete)
                            if byte == ord('\n'):
                                try:
                                    line_data = line_buffer.decode('utf-8').rstrip()
                                    if line_data:  # Only send non-empty lines
                                        lines_sent += 1
                                        print(f"[STREAM] Line {lines_sent} ready to send: {line_data}", flush=True)
                                        await self._send_log_to_backend(execution_id, line_data)
                                except UnicodeDecodeError:
                                    # Handle non-UTF8 output gracefully
                                    line_data = line_buffer.decode('utf-8', errors='replace').rstrip()
                                    if line_data:
                                        lines_sent += 1
                                        print(f"[STREAM] Line {lines_sent} ready to send (UTF8 error recovered): {line_data}", flush=True)
                                        await self._send_log_to_backend(execution_id, line_data)
                                
                                # Clear buffer for next line
                                line_buffer = bytearray()
                except OSError:
                    # No data available, sleep briefly
                    await asyncio.sleep(0.01)
            
            # Drain any remaining data from PTY after process ends
            print(f"[STREAM] Process ended, draining remaining PTY data", flush=True)
            try:
                while True:
                    byte_data = os.read(master_fd, 1024)
                    if not byte_data:
                        break
                    print(f"[STREAM] Drained {len(byte_data)} bytes from PTY after process exit", flush=True)
                    for byte in byte_data:
                        line_buffer.append(byte)
                        if byte == ord('\n'):
                            try:
                                line_data = line_buffer.decode('utf-8').rstrip()
                                if line_data:
                                    lines_sent += 1
                                    print(f"[STREAM] Line {lines_sent} ready to send: {line_data}", flush=True)
                                    await self._send_log_to_backend(execution_id, line_data)
                            except UnicodeDecodeError:
                                line_data = line_buffer.decode('utf-8', errors='replace').rstrip()
                                if line_data:
                                    lines_sent += 1
                                    await self._send_log_to_backend(execution_id, line_data)
                            line_buffer = bytearray()
            except OSError:
                pass  # PTY closed or no more data

            # Handle any remaining data in buffer (no trailing newline)
            print(f"[STREAM] Checking remaining buffer ({len(line_buffer)} bytes)", flush=True)
            if line_buffer:
                try:
                    line_data = line_buffer.decode('utf-8').rstrip()
                    if line_data:
                        lines_sent += 1
                        print(f"[STREAM] Final line {lines_sent}: {line_data}", flush=True)
                        await self._send_log_to_backend(execution_id, line_data)
                except UnicodeDecodeError:
                    line_data = line_buffer.decode('utf-8', errors='replace').rstrip()
                    if line_data:
                        lines_sent += 1
                        print(f"[STREAM] Final line {lines_sent} (UTF8 error recovered): {line_data}", flush=True)
                        await self._send_log_to_backend(execution_id, line_data)
            
            # Close the pty master fd
            os.close(master_fd)
            
            # Wait for process to complete
            exit_code = process.wait()
            print(f"[STREAM] Process completed with exit code: {exit_code}, total lines sent: {lines_sent}", flush=True)
            
            # Update status
            with self._lock:
                if execution_id in self.job_status:
                    self.job_status[execution_id].update({
                        "status": "completed" if exit_code == 0 else "failed",
                        "exit_code": exit_code
                    })
                
                # Remove from running processes
                if execution_id in self.running_processes:
                    del self.running_processes[execution_id]
            
            # Notify backend of completion
            await self._notify_backend(execution_id, 
                                     "completed" if exit_code == 0 else "failed",
                                     exit_code=exit_code)
            
        except Exception as e:
            # Handle streaming error
            with self._lock:
                if execution_id in self.job_status:
                    self.job_status[execution_id]["status"] = "failed"
                if execution_id in self.running_processes:
                    del self.running_processes[execution_id]
            
            await self._notify_backend(execution_id, "failed", error=f"Stream error: {e}")
    
    async def _notify_backend(self, execution_id: str, status: str, 
                            pid: Optional[int] = None, 
                            exit_code: Optional[int] = None,
                            error: Optional[str] = None):
        """Notify backend of job status change"""
        try:
            payload = {
                "execution_id": execution_id,
                "status": status
            }
            
            if exit_code is not None:
                payload["exit_code"] = exit_code
            if error:
                payload["error"] = error
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.backend_url}/api/node/status",
                    json=payload,
                    timeout=10.0
                )
                response.raise_for_status()
                
        except Exception as e:
            output.error(f"Failed to notify backend for execution {execution_id}: {e}")
    
    def get_status(self, execution_id: str) -> StatusResponse:
        """Get job status"""
        with self._lock:
            if execution_id not in self.job_status:
                raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
            
            status_info = self.job_status[execution_id]
            return StatusResponse(
                execution_id=execution_id,
                status=status_info["status"],
                exit_code=status_info.get("exit_code"),
                pid=status_info.get("pid")
            )
    
    def cancel_job(self, execution_id: str) -> Dict[str, Any]:
        """Cancel running job"""
        with self._lock:
            if execution_id not in self.running_processes:
                raise HTTPException(status_code=404, detail=f"Execution {execution_id} not running")
            
            process = self.running_processes[execution_id]
            
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        
        with self._lock:
            if execution_id in self.running_processes:
                del self.running_processes[execution_id]
            if execution_id in self.job_status:
                self.job_status[execution_id]["status"] = "cancelled"
        
        # Notify backend
        asyncio.create_task(self._notify_backend(execution_id, "failed", error="Job cancelled"))
        
        return {"execution_id": execution_id, "cancelled": True}
    
    def get_health(self) -> HealthResponse:
        """Get worker health status"""
        with self._lock:
            running_count = len(self.running_processes)
        
        return HealthResponse(
            status="healthy",
            running_jobs=running_count,
            max_jobs=self.max_jobs
        )
    
    def update_config(self, config: ConfigRequest) -> ConfigResponse:
        """Update worker configuration"""
        with self._lock:
            self.max_jobs = config.max_jobs
            output.info(f"Worker configuration updated: max_jobs={self.max_jobs}")
        
        return ConfigResponse(max_jobs=self.max_jobs)
    
    async def start_redis_logger(self):
        """Start Redis logger connection"""
        self._redis_connected = self._redis_logger.connect()
        if self._redis_connected:
            output.info("Redis logger connection established")
        else:
            output.warning("Redis logger connection failed, will retry on first log send")
    
    async def stop_redis_logger(self):
        """Stop Redis logger connection"""
        self._redis_logger.disconnect()
        self._redis_connected = False
        output.info("Redis logger disconnected")
    
    async def _maintain_websocket_connection(self):
        """Maintain WebSocket connection with reconnection logic"""
        while True:
            try:
                await self._connect_websocket()
                # Connection successful, reset reconnect delay
                self._reconnect_delay = 1.0
                
                # Flush any buffered logs
                await self._flush_log_buffer()
                
                # Keep connection alive
                await self._websocket.wait_closed()
                
            except Exception as e:
                output.error(f"WebSocket connection error: {e}")
                
                async with self._websocket_lock:
                    self._websocket = None
                    self._websocket_connected = False
                
                # Exponential backoff for reconnection
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
                output.info(f"Attempting WebSocket reconnection in {self._reconnect_delay}s")
    
    async def _connect_websocket(self):
        """Establish WebSocket connection to backend"""
        # Convert HTTP URL to WebSocket URL
        ws_url = self.backend_url.replace('http://', 'ws://').replace('https://', 'wss://')
        ws_url += '/api/node/logs'
        
        output.info(f"Connecting WebSocket to {ws_url}")
        
        async with self._websocket_lock:
            # Configure WebSocket with longer timeouts to prevent keepalive failures
            self._websocket = await websockets.connect(
                ws_url,
                ping_interval=30,  # Send ping every 30 seconds (default: 20)
                ping_timeout=20,   # Wait 20 seconds for pong (default: 20)
                close_timeout=10   # Wait 10 seconds for close (default: 10)
            )
            self._websocket_connected = True
            output.info("WebSocket connected to backend logger service")
    
    async def _flush_log_buffer(self):
        """Send any buffered log messages"""
        if not self._log_buffer:
            return
        
        output.info(f"Flushing {len(self._log_buffer)} buffered log messages")
        
        # Send buffered logs
        for log_message in self._log_buffer[:]:
            try:
                await self._send_websocket_message(log_message)
                self._log_buffer.remove(log_message)
            except Exception as e:
                output.error(f"Failed to flush buffered log: {e}")
                break  # Stop flushing on error
    
    async def _send_websocket_message(self, message: dict):
        """Send message via WebSocket with buffering fallback"""
        try:
            async with self._websocket_lock:
                if self._websocket_connected and self._websocket:
                    await self._websocket.send(json.dumps(message))
                    return True
                else:
                    # Buffer the message for later
                    self._buffer_log_message(message)
                    return False
        except Exception as e:
            output.error(f"WebSocket send error: {e}")
            # Buffer the message and mark connection as failed
            self._buffer_log_message(message)
            async with self._websocket_lock:
                self._websocket_connected = False
            return False
    
    def _buffer_log_message(self, message: dict):
        """Buffer log message during disconnect"""
        if len(self._log_buffer) < self._max_buffer_size:
            self._log_buffer.append(message)
        else:
            # Buffer full, drop oldest message
            self._log_buffer.pop(0)
            self._log_buffer.append(message)
            output.warning("Log buffer full, dropped oldest message")
    
    async def _send_log_to_backend(self, execution_id: str, log_data: str):
        """Send log data to backend via Redis"""
        output.info(f"DEBUG: Attempting to send log for {execution_id}: {log_data[:50]}...")
        success = self._redis_logger.send_log(execution_id, log_data)
        if success:
            output.info(f"DEBUG: Successfully sent log for {execution_id}")
        else:
            # Log failure but don't block execution
            output.warning(f"DEBUG: Failed to send log to Redis for execution {execution_id}")
    
    async def _send_log_batch_to_backend(self, execution_id: str, log_lines: list):
        """Send multiple log lines to backend via Redis"""
        # Send each line individually to Redis (more efficient for Redis)
        for log_line in log_lines:
            await self._send_log_to_backend(execution_id, log_line)
    


# Global worker node instance
worker_node = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler"""
    # Startup
    global worker_node
    
    # Initialize worker node (will be set by CLI)
    if worker_node is None:
        raise RuntimeError("Worker node not initialized")
    
    # Start Redis logger connection
    await worker_node.start_redis_logger()
    
    from worker_node import __version__
    output.info(f"Worker node '{worker_node.worker_name}' v{__version__} started with Redis logging")
    yield
    
    # Shutdown
    output.info("Worker node shutting down")
    await worker_node.stop_redis_logger()


# Create FastAPI app
app = FastAPI(
    title="Dispatcher Worker Node",
    description="HTTP REST worker node for command execution",
    version="2.0.0",
    lifespan=lifespan
)


@app.post("/execute", response_model=ExecuteResponse)
async def execute_command(request: ExecuteRequest):
    """Execute command"""
    return await worker_node.execute_command(request)


@app.get("/status/{execution_id}", response_model=StatusResponse)
async def get_job_status(execution_id: str):
    """Get status of running job"""
    return worker_node.get_status(execution_id)


@app.delete("/execute/{execution_id}")
async def cancel_job(execution_id: str):
    """Cancel running job"""
    return worker_node.cancel_job(execution_id)


@app.get("/health", response_model=HealthResponse)
async def get_health():
    """Get worker health status"""
    return worker_node.get_health()


@app.put("/config", response_model=ConfigResponse)
async def update_config(request: ConfigRequest):
    """Update worker configuration"""
    return worker_node.update_config(request)




def run_server(backend_url: str, worker_name: str, host: str = "0.0.0.0", port: int = 8501, max_jobs: int = 10):
    """Start the worker node server"""
    global worker_node
    
    # Initialize worker node
    worker_node = WorkerNode(backend_url, worker_name, max_jobs)
    
    # Start server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
        "access": {
            "format": "[%(asctime)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        }
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout"
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout"
        }
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False
        },
        "uvicorn.error": {
            "level": "INFO"
        },
        "uvicorn.access": {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False
        }
    }
}
    )


if __name__ == "__main__":
    # Direct execution for testing
    run_server(
        backend_url="http://localhost:8000",
        worker_name="test-worker",
        port=8501
    )
