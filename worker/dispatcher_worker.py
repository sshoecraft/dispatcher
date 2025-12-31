#!/usr/bin/env python3
"""
Dispatcher Worker Wrapper Script
Captures worker stdout/stderr and streams to Redis for centralized logging.
"""

import sys
import os
import pty
import select
import subprocess
import signal
import threading
import json
import base64
import redis
from datetime import datetime
from typing import Optional
from worker_node.args import get_worker_name, get_backend_url_from_args, get_debug_from_args


class WorkerLogger:
    """Handles Redis logging for worker output"""
    
    def __init__(self, worker_name: str, backend_url: str = "http://localhost:8000"):
        self.worker_name = worker_name
        self.backend_url = backend_url
        self._client = None
        self._connected = False
        
        # Extract host from backend URL if Redis is on same server
        if backend_url.startswith('http://'):
            host_part = backend_url.replace('http://', '').split(':')[0]
        elif backend_url.startswith('https://'):
            host_part = backend_url.replace('https://', '').split(':')[0]
        else:
            host_part = 'localhost'
        
        # Use environment variables or defaults
        self.redis_host = os.getenv('REDIS_HOST', host_part)
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_db = int(os.getenv('REDIS_DB', 0))
        self.redis_password = os.getenv('REDIS_PASSWORD', None)

    def connect(self) -> bool:
        """Connect to Redis server with authentication"""
        try:
            self._client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=5
            )

            # Test connection
            self._client.ping()
            self._connected = True
            return True

        except Exception as e:
            print(f"Failed to connect to Redis: {e}", file=sys.stderr)
            self._connected = False
            return False
    
    def send_log(self, log_data: str) -> bool:
        """Send log data to Redis queue"""
        if not self._connected:
            if not self.connect():
                return False
        
        try:
            # Create message with worker_name and timestamp
            message = {
                "worker_name": self.worker_name,
                "timestamp": datetime.now().isoformat(),
                "message": log_data
            }
            
            # Encode message as base64
            encoded_message = base64.b64encode(json.dumps(message).encode('utf-8'))
            
            # Push to shared logs queue
            self._client.lpush('logs', encoded_message)
            return True
            
        except redis.ConnectionError:
            # Try reconnect once
            self._connected = False
            if self.connect():
                try:
                    message = {
                        "worker_name": self.worker_name,
                        "timestamp": datetime.now().isoformat(),
                        "message": log_data
                    }
                    encoded_message = base64.b64encode(json.dumps(message).encode('utf-8'))
                    self._client.lpush('logs', encoded_message)
                    return True
                except:
                    return False
            return False
            
        except Exception as e:
            print(f"Failed to send log to Redis: {e}", file=sys.stderr)
            return False
    
    def disconnect(self):
        """Disconnect from Redis server"""
        if self._client:
            try:
                self._client.close()
            except:
                pass
            finally:
                self._connected = False
                self._client = None


def run_worker_with_logging(args, worker_name: str, backend_url: str = "http://localhost:8000", debug: bool = False):
    """Run worker process and capture output via pty"""
    
    if debug:
        print(f"[WRAPPER] Starting worker with logging: {' '.join(args)}", flush=True)
    
    # Initialize logger
    logger = WorkerLogger(worker_name, backend_url)
    if debug:
        print(f"[WRAPPER] Attempting to connect to Redis at {logger.redis_host}:{logger.redis_port}", flush=True)
    
    if not logger.connect():
        if debug:
            print(f"[WRAPPER] Warning: Could not connect to Redis, logs will not be streamed", file=sys.stderr, flush=True)
        logger = None
    else:
        if debug:
            print(f"[WRAPPER] Successfully connected to Redis", flush=True)
    
    # Create pty for capturing output
    master_fd, slave_fd = pty.openpty()
    if debug:
        print(f"[WRAPPER] Created PTY: master_fd={master_fd}, slave_fd={slave_fd}", flush=True)
    
    try:
        # Start the worker process with pty
        if debug:
            print(f"[WRAPPER] Starting subprocess: {args}", flush=True)
        process = subprocess.Popen(
            args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
            close_fds=True
        )
        
        if debug:
            print(f"[WRAPPER] Process started with PID: {process.pid}", flush=True)
        
        # Close slave fd in parent process
        os.close(slave_fd)
        
        # Set master fd to non-blocking
        import fcntl
        fcntl.fcntl(master_fd, fcntl.F_SETFL, os.O_NONBLOCK)
        
        # Signal handling for graceful shutdown
        def signal_handler(signum, frame):
            try:
                # Forward signal to worker process group
                os.killpg(os.getpgid(process.pid), signum)
            except ProcessLookupError:
                pass
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Read output and stream to Redis
        buffer = ""
        bytes_read_total = 0
        if debug:
            print(f"[WRAPPER] Starting output capture loop", flush=True)
        
        while True:
            # Check if process is still running
            if process.poll() is not None:
                if debug:
                    print(f"[WRAPPER] Process ended, checking for remaining output", flush=True)
                # Process has ended, read any remaining output
                try:
                    remaining = os.read(master_fd, 4096)
                    if remaining:
                        bytes_read_total += len(remaining)
                        if debug:
                            print(f"[WRAPPER] Read final {len(remaining)} bytes (total: {bytes_read_total})", flush=True)
                        remaining_text = remaining.decode('utf-8', errors='replace')
                        buffer += remaining_text
                        
                        # Send any remaining lines
                        lines = buffer.split('\n')
                        for line in lines[:-1]:  # All complete lines
                            if line.strip() and logger:
                                if debug:
                                    print(f"[WRAPPER] Sending final line to Redis: {line}", flush=True)
                                logger.send_log(line)
                        
                        # Send final line if it exists and doesn't end with newline
                        if lines[-1].strip() and logger:
                            if debug:
                                print(f"[WRAPPER] Sending last line to Redis: {lines[-1]}", flush=True)
                            logger.send_log(lines[-1])
                            
                except OSError:
                    pass
                break
            
            # Use select to wait for data with timeout
            try:
                ready, _, _ = select.select([master_fd], [], [], 0.1)
                if ready:
                    data = os.read(master_fd, 4096)
                    if data:
                        text = data.decode('utf-8', errors='replace')
                        buffer += text
                        
                        # Send complete lines to Redis
                        lines = buffer.split('\n')
                        for line in lines[:-1]:  # All complete lines
                            if line.strip() and logger:
                                logger.send_log(line)
                        
                        buffer = lines[-1]  # Keep incomplete line in buffer
                        
            except OSError:
                # Process ended or error reading
                break
        
        # Wait for process to complete and get exit code
        return_code = process.wait()
        
        return return_code
        
    finally:
        # Clean up
        try:
            os.close(master_fd)
        except OSError:
            pass
        
        if logger:
            logger.disconnect()




def main():
    """Main entry point - wrapper around dispatcher-worker-core"""

    # Check if debug mode is enabled
    debug = get_debug_from_args()

    if debug:
        print("[WRAPPER] Dispatcher Worker wrapper starting...", flush=True)
    
    # Get worker name for logging
    worker_name = get_worker_name()
    if debug:
        print(f"[WRAPPER] Worker name: {worker_name}", flush=True)
    
    # Get backend URL from command line arguments
    backend_url = get_backend_url_from_args()
    if debug:
        print(f"[WRAPPER] Backend URL: {backend_url}", flush=True)
    
    # Prepare arguments for dispatcher-worker-core
    # Filter out --debug from args
    filtered_args = [arg for arg in sys.argv[1:] if arg != '--debug']
    core_args = ['dispatcher-worker-core'] + filtered_args
    if debug:
        print(f"[WRAPPER] Executing: {' '.join(core_args)}", flush=True)
    
    # Run worker with logging
    try:
        exit_code = run_worker_with_logging(core_args, worker_name, backend_url, debug=debug)
        if debug:
            print(f"[WRAPPER] Worker exited with code: {exit_code}", flush=True)
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n[WRAPPER] Worker interrupted", file=sys.stderr, flush=True)
        sys.exit(1)
        
    except Exception as e:
        print(f"[WRAPPER] Worker wrapper failed: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()