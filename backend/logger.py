import asyncio
import threading
import time
import base64
import os
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, AsyncGenerator
import aiofiles
import re
import json
import redis
from info import info
from output import output

class Logger:
    """
    System logger for handling Redis log streams from worker nodes.
    Embedded in backend process, manages log file writing and streaming.
    """
    
    def __init__(self):
        self._running = False
        self._thread = None
        self._log_file_handles = {}  # execution_id -> open file handle
        self._file_locks = {}  # execution_id -> asyncio.Lock
        self._lock = threading.Lock()
        self._redis_consumer_thread = None  # Thread for consuming Redis logs
        self._redis_client = None  # Redis client instance
        
    def start(self):
        """Start the system logger"""
        with self._lock:
            if not self._running:
                self._running = True
                # Ensure log directory exists
                self._ensure_log_directory()
                # Start Redis server with network binding
                self._start_redis_server()
                output.info("System logger started (Redis consumer will start after event loop is ready)")
    
    def start_redis_consumer(self):
        """Start the Redis consumer thread"""
        if self._running and not self._redis_consumer_thread:
            self._redis_consumer_thread = threading.Thread(target=self._consume_redis_logs, daemon=True)
            self._redis_consumer_thread.start()
            output.info("Redis log consumer thread started")
    
    def stop(self):
        """Stop the system logger and close all log files"""
        with self._lock:
            if self._running:
                self._running = False
                
                # Stop Redis consumer thread
                if self._redis_consumer_thread:
                    # Thread will stop when self._running = False
                    pass
                    
                # Disconnect from Redis
                if self._redis_client:
                    try:
                        self._redis_client.close()
                    except:
                        pass
                    self._redis_client = None
                
                # Close all open log files
                for execution_id, file_handle in self._log_file_handles.items():
                    try:
                        if hasattr(file_handle, 'close'):
                            file_handle.close()
                    except Exception as e:
                        output.error(f"Error closing log file for execution {execution_id}: {e}")
                
                self._log_file_handles.clear()
                self._file_locks.clear()
                output.info("System logger stopped")
    
    def _ensure_log_directory(self):
        """Ensure the logs directory exists"""
        log_dir = Path(info.prefix) / 'logs' / 'jobs'
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    
    def _get_redis_password(self):
        """Read Redis password from config file"""
        try:
            password_file = Path(info.prefix) / 'etc' / '.redis_password'
            if password_file.exists():
                return password_file.read_text().strip()
            return None
        except Exception as e:
            output.error(f"Failed to read Redis password: {e}")
            return None

    def _start_redis_server(self):
        """Start Redis server with network binding and authentication"""
        try:
            # Get Redis password
            redis_password = self._get_redis_password()

            # Check if Redis is already running on the network interface
            network_ip = info.get_local_ip()
            test_client = redis.Redis(
                host=network_ip,
                port=6379,
                password=redis_password,
                socket_connect_timeout=2
            )
            test_client.ping()
            output.info(f"Redis already running on network interface {network_ip}:6379")
            return
        except:
            # Redis not running on network interface, start it
            pass

        try:

            # Get Redis password for configuration
            redis_password = self._get_redis_password()

            # Start Redis with network binding and authentication
            redis_log = str(Path(info.prefix) / 'logs' / 'redis.log')
            redis_pid = str(Path(info.prefix) / 'tmp' / 'redis.pid')
            redis_dir = str(Path(info.prefix) / 'data')
            redis_cmd = [
                'redis-server',
                '--bind', '0.0.0.0',
                '--port', '6379',
                '--daemonize', 'yes',
                '--protected-mode', 'yes',  # Enable protected mode
                '--logfile', redis_log,
                '--pidfile', redis_pid,
                '--dir', redis_dir
            ]

            # Add authentication if password is available
            if redis_password:
                redis_cmd.extend(['--requirepass', redis_password])

            result = subprocess.run(redis_cmd, capture_output=True, text=True, check=True)
            output.info(f"Started Redis server on 0.0.0.0:6379 (log: {redis_log})")

            # Wait a moment for Redis to start
            time.sleep(2)

            # Verify connection with authentication
            network_ip = info.get_local_ip()
            test_client = redis.Redis(
                host=network_ip,
                port=6379,
                password=redis_password,
                socket_connect_timeout=5
            )
            test_client.ping()
            output.info(f"Verified Redis connection on {network_ip}:6379")

        except subprocess.CalledProcessError as e:
            output.error(f"Failed to start Redis server: {e.stderr}")
        except Exception as e:
            output.error(f"Error starting Redis server: {e}")
    
    def _parse_execution_id(self, execution_id_or_job_id) -> int:
        """
        Parse execution_id to extract job_id, or return job_id if it's already an int.
        
        Args:
            execution_id_or_job_id: Either execution_id string "queue_name:job_id" or job_id int
            
        Returns:
            job_id as integer
            
        Raises:
            ValueError: If execution_id format is invalid
        """
        if isinstance(execution_id_or_job_id, int):
            # Already a job_id, return as-is (backward compatibility)
            return execution_id_or_job_id
        elif isinstance(execution_id_or_job_id, str):
            # Parse execution_id format: "queue_name:job_id"
            try:
                queue_name, job_id_str = execution_id_or_job_id.split(':', 1)
                return int(job_id_str)
            except (ValueError, IndexError):
                raise ValueError(f"Invalid execution_id format: {execution_id_or_job_id}. Expected: queue_name:job_id")
        else:
            raise ValueError(f"Invalid execution_id type: {type(execution_id_or_job_id)}. Expected string or int")
    
    async def append_log(self, execution_id_or_job_id, log_data: str, is_base64: bool = False) -> bool:
        """
        Append log data to a job's log file using cached file handles.
        
        Args:
            execution_id_or_job_id: Either execution_id string "queue_name:job_id" or job_id int
            log_data: Log content (raw text or base64 encoded)
            is_base64: Whether log_data is base64 encoded
            
        Returns:
            True if successful, False otherwise
        """
        if not self._running:
            return False
            
        try:
            # Use execution_id as cache key (convert job_id to execution_id format if needed)
            if isinstance(execution_id_or_job_id, int):
                # For backward compatibility, convert job_id to execution_id format
                execution_id = f"unknown:{execution_id_or_job_id}"
                job_id = execution_id_or_job_id
            else:
                execution_id = execution_id_or_job_id
                job_id = self._parse_execution_id(execution_id)
            
            # Get or create lock for this execution
            if execution_id not in self._file_locks:
                self._file_locks[execution_id] = asyncio.Lock()
            
            # Decode base64 if needed
            if is_base64:
                try:
                    log_content = base64.b64decode(log_data).decode('utf-8', errors='replace')
                except Exception as e:
                    output.error(f"Failed to decode base64 log data for execution {execution_id}: {e}")
                    return False
            else:
                log_content = log_data
            
            # Ensure content ends with newline
            if not log_content.endswith('\n'):
                log_content += '\n'
            
            # Parse keywords before writing to log file
            await self._parse_keywords(job_id, log_content)
            
            # Get or open cached file handle
            async with self._file_locks[execution_id]:
                file_handle = await self._get_cached_file_handle(execution_id, job_id)
                if file_handle:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    log_line = f"[{timestamp}] {log_content}"
                    file_handle.write(log_line.encode('utf-8'))
                    # Remove blocking fsync - let OS buffer writes for better performance
                else:
                    output.error(f"Failed to get file handle for execution {execution_id}")
                    return False
            
            return True
            
        except Exception as e:
            output.error(f"Failed to append log for execution_id/job_id {execution_id_or_job_id}: {e}")
            return False
    
    async def get_log_content(self, job_id: int, follow: bool = False) -> Optional[AsyncGenerator[str, None]]:
        """
        Get log content for a job.
        
        Args:
            job_id: Job ID
            follow: If True, follow the log file (tail -f behavior)
            
        Returns:
            AsyncGenerator yielding log lines, or None if file doesn't exist
        """
        log_file_path = await self._get_job_log_path(job_id)
        
        if not log_file_path.exists():
            return None
        
        if not follow:
            # Read entire file once
            async def read_all():
                try:
                    async with aiofiles.open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = await f.read()
                        yield content
                except Exception as e:
                    output.error(f"Failed to read log file for job {job_id}: {e}")
                    yield f"Error reading log file: {e}\n"
            
            return read_all()
        
        else:
            # Follow log file (for SSE streaming)
            async def follow_log():
                try:
                    # Read existing content first
                    try:
                        async with aiofiles.open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                            existing_content = await f.read()
                            if existing_content:
                                yield existing_content
                    except Exception:
                        pass
                    
                    # Then follow for new content
                    last_size = log_file_path.stat().st_size if log_file_path.exists() else 0
                    
                    while self._running:
                        try:
                            if log_file_path.exists():
                                current_size = log_file_path.stat().st_size
                                
                                if current_size > last_size:
                                    # File has grown, read new content
                                    async with aiofiles.open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                                        await f.seek(last_size)
                                        new_content = await f.read()
                                        if new_content:
                                            yield new_content
                                        last_size = current_size
                            
                            await asyncio.sleep(0.5)  # Check every 500ms
                            
                        except Exception as e:
                            output.error(f"Error following log file for job {job_id}: {e}")
                            yield f"Error following log: {e}\n"
                            break
                            
                except Exception as e:
                    output.error(f"Failed to follow log file for job {job_id}: {e}")
                    yield f"Error starting log follow: {e}\n"
            
            return follow_log()
    
    async def get_worker_log_content(self, worker_name: str, follow: bool = False) -> Optional[AsyncGenerator[str, None]]:
        """
        Get log content for a worker.
        
        Args:
            worker_name: Worker name
            follow: If True, follow the log file (tail -f behavior)
            
        Returns:
            AsyncGenerator yielding log lines, or None if file doesn't exist
        """
        log_file_path = self._get_worker_log_path(worker_name)
        
        if not log_file_path.exists():
            return None
        
        if not follow:
            # Read entire file once
            async def read_all():
                try:
                    async with aiofiles.open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = await f.read()
                        yield content
                except Exception as e:
                    output.error(f"Failed to read worker log file for {worker_name}: {e}")
                    yield f"Error reading log file: {e}\n"
            
            return read_all()
        
        else:
            # Follow log file (for SSE streaming)
            async def follow_log():
                try:
                    # Read existing content first
                    try:
                        async with aiofiles.open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                            existing_content = await f.read()
                            if existing_content:
                                yield existing_content
                    except Exception:
                        pass
                    
                    # Then follow for new content
                    last_size = log_file_path.stat().st_size if log_file_path.exists() else 0
                    
                    while self._running:
                        try:
                            if log_file_path.exists():
                                current_size = log_file_path.stat().st_size
                                
                                if current_size > last_size:
                                    # File has grown, read new content
                                    async with aiofiles.open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                                        await f.seek(last_size)
                                        new_content = await f.read()
                                        if new_content:
                                            yield new_content
                                        last_size = current_size
                            
                            await asyncio.sleep(0.5)  # Check every 500ms
                            
                        except Exception as e:
                            output.error(f"Error following worker log file for {worker_name}: {e}")
                            yield f"Error following log: {e}\n"
                            break
                            
                except Exception as e:
                    output.error(f"Failed to follow worker log file for {worker_name}: {e}")
                    yield f"Error starting log follow: {e}\n"
            
            return follow_log()
    
    async def clear_worker_log(self, worker_name: str) -> bool:
        """
        Clear a worker's log file.
        
        Args:
            worker_name: Worker name
            
        Returns:
            True if successful, False otherwise
        """
        try:
            log_file_path = self._get_worker_log_path(worker_name)
            
            # Close cached file handle if it exists
            cache_key = f"worker:{worker_name}"
            if cache_key in self._log_file_handles:
                try:
                    self._log_file_handles[cache_key].close()
                    del self._log_file_handles[cache_key]
                except:
                    pass
            
            # Clear the file by opening in write mode
            if log_file_path.exists():
                open(log_file_path, 'w').close()
                output.info(f"Cleared worker log file for {worker_name}")
            
            return True
            
        except Exception as e:
            output.error(f"Failed to clear worker log for {worker_name}: {e}")
            return False
    
    async def close_job_log(self, job_id: int):
        """Close and clean up resources for a job's log"""
        if job_id in self._file_locks:
            async with self._file_locks[job_id]:
                pass  # Just wait for any pending writes to complete
            
        # Clean up the lock
        if job_id in self._file_locks:
            del self._file_locks[job_id]
        
        output.info(f"Closed log resources for job {job_id}")
    
    async def close_log(self, execution_id: str):
        """Close and clean up cached file handle for an execution_id"""
        try:
            if execution_id in self._log_file_handles:
                file_handle = self._log_file_handles[execution_id]
                
                # Get lock for this execution if it exists
                if execution_id in self._file_locks:
                    async with self._file_locks[execution_id]:
                        try:
                            file_handle.flush()  # Ensure all data is written
                            file_handle.close()
                        except Exception as e:
                            output.error(f"Error closing log file for execution {execution_id}: {e}")
                        
                        # Remove from cache
                        del self._log_file_handles[execution_id]
                else:
                    # No lock exists, close directly
                    try:
                        file_handle.flush()
                        file_handle.close()
                    except Exception as e:
                        output.error(f"Error closing log file for execution {execution_id}: {e}")
                    
                    # Remove from cache
                    del self._log_file_handles[execution_id]
                
                # Clean up the lock as well
                if execution_id in self._file_locks:
                    del self._file_locks[execution_id]
                
                output.info(f"Closed and cleaned up log resources for execution {execution_id}")
            else:
                output.warning(f"No cached log file handle found for execution {execution_id}")
                
        except Exception as e:
            output.error(f"Failed to close log for execution {execution_id}: {e}")
    
    async def _parse_keywords(self, job_id: int, log_content: str):
        """Parse log content for PROGRESS=, ERROR=, and RESULT= keywords and update job accordingly"""
        try:
            # Import job here to avoid circular imports
            from job import job
            
            # Check for PROGRESS= patterns
            progress_match = re.search(r'PROGRESS=(\d+)', log_content)
            if progress_match:
                progress_val = int(progress_match.group(1))
                output.debug(f"📊 Found PROGRESS={progress_val} in job {job_id} log")
                if 0 <= progress_val <= 100:
                    await self._update_job_progress(job_id, progress_val)
                else:
                    output.warning(f"Invalid progress value {progress_val} for job {job_id}")
            
            # Check for RESULT= patterns (handles both RESULT={...} and RESULT='...' formats)
            result_match = re.search(r"RESULT=(?:'([^']*)'|({.*}))", log_content)
            if result_match:
                try:
                    # Get whichever group matched (quoted or unquoted)
                    result_str = result_match.group(1) or result_match.group(2)
                    result_json = json.loads(result_str)
                    output.debug(f"📋 Found RESULT in job {job_id} log")
                    await self._update_job_result(job_id, result_json)
                except json.JSONDecodeError:
                    output.warning(f"Invalid RESULT JSON in job {job_id}: {result_str}")
            
            # Check for ERROR= patterns (handles both ERROR={...} and ERROR='...' formats like RESULT)
            error_match = re.search(r"ERROR=(?:'([^']*)'|({.*}))", log_content)
            if error_match:
                try:
                    # Get whichever group matched (quoted or unquoted)
                    error_str = error_match.group(1) or error_match.group(2)
                    error_json = json.loads(error_str)
                    output.debug(f"❌ Found ERROR in job {job_id} log")
                    
                    # Extract message field if it exists, otherwise use the full JSON as string
                    if isinstance(error_json, dict) and 'message' in error_json:
                        error_message = error_json['message']
                    else:
                        # If no message field, convert the whole JSON to string
                        error_message = json.dumps(error_json)
                    
                    await self._update_job_error(job_id, error_message)
                except json.JSONDecodeError:
                    output.warning(f"Invalid ERROR JSON in job {job_id}: {error_str}")
                    # If not valid JSON, use the raw string as error message
                    await self._update_job_error(job_id, error_str)
                
        except Exception as e:
            output.error(f"Error parsing keywords for job {job_id}: {e}")
    
    async def _update_job_progress(self, job_id: int, progress: int):
        """Update job progress in database"""
        try:
            from job import job
            job.update_progress(job_id, progress)
        except Exception as e:
            output.error(f"Failed to update progress for job {job_id}: {e}")
    
    async def _update_job_result(self, job_id: int, result: dict):
        """Update job result in database"""
        try:
            from job import job
            job.update_result(job_id, result)
        except Exception as e:
            output.error(f"Failed to update result for job {job_id}: {e}")
    
    async def _update_job_error(self, job_id: int, error_message: str):
        """Update job error message in database (only if not already set)"""
        try:
            from job import job
            job.update_error(job_id, error_message)
        except Exception as e:
            output.error(f"Failed to update error for job {job_id}: {e}")
    
    
    async def _get_job_log_path(self, job_id: int) -> Path:
        """Get log file path from job record, fallback to generated path"""
        try:
            from job import job
            from db import db
            
            with db.get_session() as session:
                job_record = job.get_by_id(session, job_id)
                if job_record and job_record.log_file_path:
                    return Path(job_record.log_file_path)
                else:
                    # Fallback to generated path if job record doesn't have path
                    log_dir = self._ensure_log_directory()
                    fallback_path = log_dir / f"{job_id}.log"
                    output.warning(f"Job {job_id} missing log_file_path, using fallback: {fallback_path}")
                    return fallback_path
        except Exception as e:
            # If we can't access the database, fallback to generated path
            output.error(f"Failed to get log path for job {job_id}: {e}")
            log_dir = self._ensure_log_directory()
            return log_dir / f"{job_id}.log"
    
    async def _get_cached_file_handle(self, execution_id: str, job_id: int):
        """Get cached file handle for execution_id, open if not cached"""
        # Check if already cached
        if execution_id in self._log_file_handles:
            return self._log_file_handles[execution_id]
        
        try:
            # Not cached, need to open the file
            log_file_path = await self._get_job_log_path(job_id)
            
            # Open file in append mode with no buffering for real-time output
            file_handle = open(log_file_path, 'ab', buffering=0)  # Binary mode for unbuffered
            
            # Cache the handle
            self._log_file_handles[execution_id] = file_handle
            
            output.info(f"Opened log file for execution {execution_id}: {log_file_path}")
            return file_handle
            
        except Exception as e:
            output.error(f"Failed to open log file for execution {execution_id}: {e}")
            return None
    
    def _initialize_redis(self) -> bool:
        """Initialize Redis connection with authentication"""
        try:
            # Use network IP for Redis connection to allow remote workers to connect
            redis_host = info.get_local_ip()
            redis_password = self._get_redis_password()

            self._redis_client = redis.Redis(
                host=redis_host,
                port=6379,
                db=0,
                password=redis_password,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=10
            )

            # Test connection
            self._redis_client.ping()
            output.info(f"Redis connection established for logger at {redis_host}:6379")
            return True

        except Exception as e:
            output.error(f"Failed to connect to Redis at {redis_host}:6379: {e}")
            return False
    
    def _consume_redis_logs(self):
        """
        Background thread to consume logs from single Redis logs queue.
        Pulls logs from Redis and writes to files.
        """
        output.info("Redis log consumer thread running")
        
        # Wait a bit before trying to connect
        time.sleep(1)
        
        # Initialize Redis connection
        if not self._initialize_redis():
            output.error("Failed to connect to Redis for log consumption")
            return
        
        output.info(f"Connected to Redis at {info.get_local_ip()}:6379")
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self._running:
            try:
                # BRPOP from single logs queue - block forever (daemon thread dies with parent)
                result = self._redis_client.brpop(['logs'], timeout=0)
                
                if result:
                    queue_key, encoded_message = result
                    
                    # Decode base64 message
                    try:
                        message_json = base64.b64decode(encoded_message).decode('utf-8')
                        message_data = json.loads(message_json)
                        
                        # Check for either execution_id (job logs) or worker_name (worker logs)
                        execution_id = message_data.get('execution_id')
                        worker_name = message_data.get('worker_name')
                        timestamp = message_data.get('timestamp')
                        log_data = message_data.get('message')
                        
                        if execution_id and log_data:
                            # Process job log message synchronously
                            self._append_log_sync(execution_id, log_data)
                            
                            # Reset error counter on success
                            consecutive_errors = 0
                        elif worker_name and log_data:
                            # Process worker log message synchronously
                            self._append_worker_log_sync(worker_name, log_data)
                            
                            # Reset error counter on success
                            consecutive_errors = 0
                        else:
                            output.warning("Invalid message format: missing execution_id/worker_name or message")
                            
                    except (json.JSONDecodeError, ValueError) as e:
                        output.error(f"Failed to decode log message: {e}")
                        
                else:
                    # No data available (timeout), this is normal
                    consecutive_errors = 0
                    
            except redis.ConnectionError as e:
                consecutive_errors += 1
                output.error(f"Redis connection error ({consecutive_errors}/{max_consecutive_errors}): {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    output.error("Too many consecutive Redis errors, attempting reconnection...")
                    if not self._initialize_redis():
                        output.error("Failed to reconnect to Redis, stopping consumer...")
                        break
                    consecutive_errors = 0
                else:
                    time.sleep(2 ** min(consecutive_errors, 4))  # Exponential backoff
                    
            except redis.TimeoutError:
                # BRPOP timeout is normal, don't count as error
                consecutive_errors = 0
                    
            except Exception as e:
                consecutive_errors += 1
                output.error(f"Unexpected error in Redis consumer: {e} (error {consecutive_errors}/{max_consecutive_errors})")
                
                if consecutive_errors >= max_consecutive_errors:
                    output.error("Too many consecutive errors in Redis consumer, stopping...")
                    break
                
                # Wait before retrying
                time.sleep(1)
        
        output.info("Redis log consumer stopped")
    
    def _get_log_file_handle(self, execution_id: str):
        """Get or create file handle for execution_id"""
        if execution_id in self._log_file_handles:
            return self._log_file_handles[execution_id]
        
        try:
            # Parse job_id from execution_id
            job_id = self._parse_execution_id(execution_id)
            
            # Get log file path
            from db import db
            from job import job
            
            with db.get_session() as session:
                job_record = job.get_by_id(session, job_id)
                if job_record and job_record.log_file_path:
                    log_file_path = Path(job_record.log_file_path)
                else:
                    # Fallback to generated path
                    log_dir = self._ensure_log_directory()
                    log_file_path = log_dir / f"{job_id}.log"
            
            # Ensure directory exists
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Open file in append mode, unbuffered
            file_handle = open(log_file_path, 'ab', buffering=0)
            
            # Cache the handle
            self._log_file_handles[execution_id] = file_handle
            
            output.info(f"Opened log file for execution {execution_id}: {log_file_path}")
            return file_handle
            
        except Exception as e:
            output.error(f"Failed to open log file for execution {execution_id}: {e}")
            return None
    
    def _append_log_sync(self, execution_id: str, log_data: str):
        """
        Synchronous version of append_log for use by Redis consumer thread.
        This is a simplified version that writes directly to files without async operations.
        """
        try:
            # Get or create file handle
            file_handle = self._log_file_handles.get(execution_id)

            # Check if handle exists but is closed (can happen if close_log was called)
            if file_handle and file_handle.closed:
                # Remove stale handle from cache and get a fresh one
                del self._log_file_handles[execution_id]
                file_handle = None

            if not file_handle:
                file_handle = self._get_log_file_handle(execution_id)
                if not file_handle:
                    return False

            # Write log data (timestamp already included from worker)
            log_line = f"{log_data}\n"
            
            # Write to file (using sync I/O in thread is fine)
            file_handle.write(log_line.encode('utf-8'))
            file_handle.flush()  # Ensure real-time viewing
            os.fsync(file_handle.fileno())  # Force to disk (safe in separate thread)
            
            # Parse keywords for progress/result updates
            job_id = self._parse_execution_id(execution_id)
            self._parse_keywords_sync(job_id, log_data)
            
            return True
            
        except Exception as e:
            output.error(f"Error in sync log append for {execution_id}: {e}")
            return False
    
    def _append_worker_log_sync(self, worker_name: str, log_data: str):
        """
        Synchronous version of append_log for worker logs.
        Writes to logs/workers/{worker_name}.log files.
        """
        try:
            # Get or create file handle for worker
            cache_key = f"worker:{worker_name}"
            file_handle = self._log_file_handles.get(cache_key)

            # Check if handle exists but is closed
            if file_handle and file_handle.closed:
                del self._log_file_handles[cache_key]
                file_handle = None

            if not file_handle:
                file_handle = self._get_worker_log_file_handle(worker_name)
                if not file_handle:
                    return False

            # Add timestamp and write log data
            timestamp = datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')
            log_line = f"{timestamp} {log_data}\n"
            
            # Write to file (using sync I/O in thread is fine)
            file_handle.write(log_line.encode('utf-8'))
            file_handle.flush()
            os.fsync(file_handle.fileno())  # Force to disk
            
            return True
            
        except Exception as e:
            output.error(f"Error in worker log append for {worker_name}: {e}")
            return False
    
    def _get_worker_log_file_handle(self, worker_name: str):
        """Get or create file handle for worker logs"""
        cache_key = f"worker:{worker_name}"
        
        if cache_key in self._log_file_handles:
            return self._log_file_handles[cache_key]
        
        try:
            # Get worker log file path
            log_file_path = self._get_worker_log_path(worker_name)
            
            # Ensure directory exists
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Open file in append mode, unbuffered
            file_handle = open(log_file_path, 'ab', buffering=0)
            
            # Cache the handle
            self._log_file_handles[cache_key] = file_handle
            
            output.info(f"Opened worker log file for {worker_name}: {log_file_path}")
            return file_handle
            
        except Exception as e:
            output.error(f"Failed to open worker log file for {worker_name}: {e}")
            return None
    
    def _get_worker_log_path(self, worker_name: str) -> Path:
        """Get the log file path for a worker"""
        log_dir = Path(info.prefix) / 'logs' / 'workers'
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"{worker_name.lower()}.log"
    
    def _parse_keywords_sync(self, job_id: int, log_content: str):
        """Synchronous version of keyword parsing for Redis consumer thread"""
        try:
            from db import db
            from job import job
            
            # Check for PROGRESS= patterns
            progress_match = re.search(r'PROGRESS=(\d+)', log_content)
            if progress_match:
                progress_val = int(progress_match.group(1))
                output.debug(f"📊 Found PROGRESS={progress_val} in job {job_id} log")
                if 0 <= progress_val <= 100:
                    # Update job progress in database
                    with db.get_session() as session:
                        job_record = job.get_by_id(session, job_id)
                        if job_record:
                            job_record.progress = progress_val
                            session.commit()
                            output.debug(f"Updated job {job_id} progress to {progress_val}%")
                else:
                    output.warning(f"Invalid progress value {progress_val} for job {job_id}")
            
            # Check for RESULT= patterns
            result_match = re.search(r"RESULT=(?:'([^']*)'|({.*}))", log_content)
            if result_match:
                try:
                    result_str = result_match.group(1) or result_match.group(2)
                    result_data = json.loads(result_str) if result_str.startswith('{') else result_str
                    
                    # Update job result in database
                    with db.get_session() as session:
                        job_record = job.get_by_id(session, job_id)
                        if job_record:
                            job_record.result = result_data if isinstance(result_data, dict) else {"value": result_data}
                            session.commit()
                            output.debug(f"Updated job {job_id} result")
                except json.JSONDecodeError:
                    output.warning(f"Invalid RESULT JSON in log: {result_match.group(0)}")
            
            # Check for ERROR= patterns (handles both ERROR={...} and ERROR='...' formats)
            error_match = re.search(r"ERROR=(?:'([^']*)'|({.*}))", log_content)
            if error_match:
                try:
                    # Get whichever group matched (quoted or unquoted)
                    error_str = error_match.group(1) or error_match.group(2)
                    error_json = json.loads(error_str)
                    
                    # Extract message field if it exists, otherwise use the full JSON as string
                    if isinstance(error_json, dict) and 'message' in error_json:
                        error_message = error_json['message']
                    else:
                        # If no message field, convert the whole JSON to string
                        error_message = json.dumps(error_json)
                        
                except json.JSONDecodeError:
                    # If not valid JSON, use the raw string as error message
                    error_message = error_str
                
                with db.get_session() as session:
                    job_record = job.get_by_id(session, job_id)
                    if job_record:
                        job_record.error_message = error_message
                        job_record.status = "Failed"
                        session.commit()
                        output.warning(f"Job {job_id} reported error: {error_message}")
                        
        except Exception as e:
            output.error(f"Error parsing keywords for job {job_id}: {e}")


# Global logger instance for log collection
logger = Logger()
