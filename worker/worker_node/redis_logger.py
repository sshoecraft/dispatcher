"""
Redis-based logger for worker nodes
Replaces WebSocket connection with simple Redis LPUSH
"""

import redis
import os
import json
import base64
from datetime import datetime
from typing import Optional
from .output import output

class RedisLogger:
    """
    Simple Redis logger for worker nodes.
    Pushes log messages to Redis queue for backend consumption.
    """
    
    def __init__(self, backend_url: str):
        """
        Initialize Redis logger.
        
        Args:
            backend_url: Backend URL (used to extract host if Redis is on same server)
        """
        # Extract host from backend URL if Redis is on same server
        # Format: http://host:port -> host
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

        self._client = None
        self._connected = False
        
    def connect(self) -> bool:
        """
        Connect to Redis server with authentication.

        Returns:
            True if connected successfully, False otherwise
        """
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
            output.info(f"Connected to Redis for logging at {self.redis_host}:{self.redis_port}")
            return True

        except Exception as e:
            output.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """Disconnect from Redis server"""
        if self._client:
            try:
                self._client.close()
                output.info("Disconnected from Redis logger")
            except:
                pass
            finally:
                self._connected = False
                self._client = None
    
    def send_log(self, execution_id: str, log_data: str, debug: bool = False) -> bool:
        """
        Send log data to Redis queue.
        
        Args:
            execution_id: Execution ID (format: "queue_name:job_id")
            log_data: Log line to send
            debug: Enable debug output
            
        Returns:
            True if successful, False otherwise
        """
        # Print to stdout what we're about to send
        if debug:
            print(f"[REDIS-LOG] Sending to Redis for {execution_id}:", flush=True)
            print(f"[REDIS-LOG] Data: {log_data}", flush=True)
        
        if not self._connected:
            if debug:
                print(f"[REDIS-LOG] Not connected, attempting to connect...", flush=True)
            if not self.connect():
                if debug:
                    print(f"[REDIS-LOG] ❌ Failed to connect to Redis", flush=True)
                return False
        
        try:
            # Create message with execution_id and timestamp
            message = {
                "execution_id": execution_id,
                "timestamp": datetime.now().isoformat(),
                "message": log_data
            }
            
            if debug:
                print(f"[REDIS-LOG] Message object: {json.dumps(message)}", flush=True)
            
            # Encode message as base64
            encoded_message = base64.b64encode(json.dumps(message).encode('utf-8'))
            
            if debug:
                print(f"[REDIS-LOG] Encoded message (base64): {encoded_message[:100]}...", flush=True)
            
            # Push to single shared logs queue
            result = self._client.lpush('logs', encoded_message)
            if debug:
                print(f"[REDIS-LOG] ✅ Redis lpush successful! Result: {result}, Queue: 'logs'", flush=True)
            output.info(f"DEBUG: Redis lpush result: {result} for execution_id {execution_id}")
            return True
            
        except redis.ConnectionError as e:
            # Try reconnect once
            if debug:
                print(f"[REDIS-LOG] ⚠️  Redis connection lost: {e}", flush=True)
            output.warning("Redis connection lost, attempting reconnect...")
            self._connected = False
            if self.connect():
                try:
                    message = {
                        "execution_id": execution_id,
                        "timestamp": datetime.now().isoformat(),
                        "message": log_data
                    }
                    encoded_message = base64.b64encode(json.dumps(message).encode('utf-8'))
                    result = self._client.lpush('logs', encoded_message)
                    if debug:
                        print(f"[REDIS-LOG] ✅ Redis lpush successful after reconnect! Result: {result}", flush=True)
                    return True
                except Exception as e2:
                    if debug:
                        print(f"[REDIS-LOG] ❌ Failed after reconnect: {e2}", flush=True)
                    return False
            if debug:
                print(f"[REDIS-LOG] ❌ Could not reconnect to Redis", flush=True)
            return False
            
        except Exception as e:
            if debug:
                print(f"[REDIS-LOG] ❌ Failed to send log to Redis: {e}", flush=True)
            output.error(f"Failed to send log to Redis: {e}")
            return False
    
    def flush(self):
        """Flush any pending operations (no-op for Redis, kept for compatibility)"""
        pass