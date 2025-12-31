from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from threading import Lock, Thread
from contextlib import contextmanager
import json
import asyncio
import httpx
import subprocess
import sys
import os
import signal
import time
import base64
import tempfile
import socket
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import paramiko
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from info import info
from output import output
from db import db
from models import Worker as WorkerModel

class DeploymentStatus:
    """Track deployment progress for workers"""
    def __init__(self):
        self.deployments = {}  # deployment_id -> status
        self.lock = Lock()
    
    def start_deployment(self, deployment_id: str, worker_name: str) -> None:
        with self.lock:
            self.deployments[deployment_id] = {
                'worker_name': worker_name,
                'current_step': 'Starting deployment...',
                'step_number': 0,
                'total_steps': 7,
                'status': 'deploying',
                'started_at': datetime.now(),
                'last_updated': datetime.now(),
                'error': None
            }
    
    def update_step(self, deployment_id: str, step: str, step_number: int) -> None:
        with self.lock:
            if deployment_id in self.deployments:
                self.deployments[deployment_id].update({
                    'current_step': step,
                    'step_number': step_number,
                    'last_updated': datetime.now()
                })
    
    def complete_deployment(self, deployment_id: str, success: bool, error: str = None) -> None:
        with self.lock:
            if deployment_id in self.deployments:
                self.deployments[deployment_id].update({
                    'status': 'success' if success else 'error',
                    'error': error,
                    'last_updated': datetime.now()
                })
    
    def get_status(self, deployment_id: str) -> Optional[dict]:
        with self.lock:
            status = self.deployments.get(deployment_id)
            if status:
                # Check for timeout (>2 minutes)
                if datetime.now() - status['last_updated'] > timedelta(minutes=2):
                    status['status'] = 'timeout'
                    status['error'] = 'Deployment timed out'
            return status
    
    def cleanup_deployment(self, deployment_id: str) -> None:
        with self.lock:
            self.deployments.pop(deployment_id, None)

# Global deployment status tracker
deployment_status = DeploymentStatus()

class WorkerCreateRequest(BaseModel):
    """Request model for creating a worker"""
    name: str = Field(..., description="Worker name")
    worker_type: str = Field("remote", description="Worker type (local or remote)")
    hostname: Optional[str] = Field(None, description="Worker hostname")
    ip_address: Optional[str] = Field(None, description="Worker IP address")
    port: Optional[int] = Field(None, description="Worker HTTP port (defaults to 8500+worker_id)")
    ssh_user: Optional[str] = Field(None, description="SSH username")
    auth_method: str = Field("key", description="Authentication method (key or password)")
    ssh_private_key: Optional[str] = Field(None, description="SSH private key")
    password: Optional[str] = Field(None, description="SSH password")
    provision: bool = Field(False, description="Auto-provision worker")
    max_jobs: int = Field(10, description="Maximum concurrent jobs")

class WorkerUpdateRequest(BaseModel):
    """Request model for updating a worker"""
    name: Optional[str] = Field(None, description="Worker name")
    worker_type: Optional[str] = Field(None, description="Worker type (local or remote)")
    hostname: Optional[str] = Field(None, description="Worker hostname")
    ip_address: Optional[str] = Field(None, description="Worker IP address")
    port: Optional[int] = Field(None, description="Worker HTTP port")
    ssh_user: Optional[str] = Field(None, description="SSH username")
    auth_method: Optional[str] = Field(None, description="Authentication method (key or password)")
    ssh_private_key: Optional[str] = Field(None, description="SSH private key")
    password: Optional[str] = Field(None, description="SSH password")
    provision: Optional[bool] = Field(None, description="Auto-provision worker")
    max_jobs: Optional[int] = Field(None, description="Maximum concurrent jobs")

class Worker:
    def __init__(self):
        self._lock = Lock()
        self._initialized = False
        self._workers = []  # List of worker configurations (includes process info for local workers)
        self._manager_running = False
        self._manager_thread = None
        self._monitoring_interval = 30  # Default monitoring interval in seconds
    
    def initialize(self):
        """Initialize worker - called at startup"""
        try:
            output.info("DEBUG: Worker initialize() called")
            
            # Load all workers from database into memory
            output.info("DEBUG: Loading workers from database")
            self._load_workers_from_database()
            
            # Start all local workers that should be running
            output.info("DEBUG: Calling _start_all_workers()")
            self._start_all_workers()
            
            # Start health monitoring thread
            output.info("DEBUG: Calling _start_health_monitor()")
            self._start_health_monitor()
            
            self._initialized = True
            output.info("Worker initialized successfully")
        except Exception as e:
            output.error(f"Failed to initialize worker: {e}")
            raise
    
    def _get_prefix(self) -> str:
        """Get the PREFIX environment variable or default"""
        return os.environ.get('PREFIX', os.path.expanduser('~/.dispatcher'))
    
    def _resolve_hostname_to_ip(self, hostname: str) -> str:
        """Resolve hostname to IP address via DNS lookup.
        
        Args:
            hostname: The hostname to resolve
            
        Returns:
            The resolved IP address
            
        Raises:
            Exception: If hostname cannot be resolved
        """
        try:
            output.info(f"Resolving hostname '{hostname}' to IP address")
            ip_address = socket.gethostbyname(hostname)
            output.info(f"Resolved '{hostname}' to IP address: {ip_address}")
            return ip_address
        except socket.gaierror as e:
            error_msg = f"Failed to resolve hostname '{hostname}': {e}"
            output.error(error_msg)
            raise Exception(error_msg)
    
    def _get_key_identifier(self, hostname: str, ssh_user: str) -> str:
        """Get key identifier based on user-entered hostname for SSH key naming.
        
        Args:
            hostname: The original hostname as entered by user in Add Worker
            ssh_user: SSH username
            
        Returns:
            Key identifier string in format "hostname-username" 
        """
        # Always use the hostname exactly as the user entered it for key naming
        # If it's a FQDN, use just the short hostname part
        if hostname and '.' in hostname:
            # For hostnames with dots (FQDN or IP), use the first part
            key_prefix = hostname.split('.')[0]
        elif hostname:
            # Single word hostname - use as-is
            key_prefix = hostname
        else:
            # Fallback for missing hostname
            key_prefix = "unknown"
        
        key_id = f"{key_prefix}-{ssh_user}"
        output.info(f"Key identifier for hostname '{hostname}': {key_id}")
        return key_id
    
    def _generate_worker_ssh_key(self, hostname: str, ssh_user: str) -> Dict[str, str]:
        """Generate a unique ED25519 SSH key pair for a remote worker.
        
        Args:
            hostname: Worker hostname
            ssh_user: SSH username
            
        Returns:
            Dict with 'private_key_path', 'public_key_path', 'private_key', 'public_key'
        """
        try:
            # Generate ED25519 key pair
            private_key = ed25519.Ed25519PrivateKey.generate()
            
            # Serialize private key
            private_key_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.OpenSSH,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            # Serialize public key
            public_key = private_key.public_key()
            public_key_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.OpenSSH,
                format=serialization.PublicFormat.OpenSSH
            )
            
            # Use centralized key identifier logic
            key_id = self._get_key_identifier(hostname, ssh_user)
            public_key_str = public_key_bytes.decode('utf-8') + f" dispatcher-worker-{key_id}"
            
            # Create key file paths in $PREFIX/etc/
            prefix = self._get_prefix()
            ssh_keys_dir = Path(prefix) / "etc" / "ssh_keys"
            ssh_keys_dir.mkdir(parents=True, exist_ok=True)
            
            private_key_path = ssh_keys_dir / f"{key_id}.id"
            public_key_path = ssh_keys_dir / f"{key_id}.pub"
            
            # Write private key file
            with open(private_key_path, 'w') as f:
                f.write(private_key_bytes.decode('utf-8'))
            os.chmod(private_key_path, 0o600)  # Secure permissions
            
            # Write public key file
            with open(public_key_path, 'w') as f:
                f.write(public_key_str)
            os.chmod(public_key_path, 0o644)  # Read-only for owner, readable by group
            
            output.info(f"Generated SSH key pair for worker {hostname} (user: {ssh_user})")
            output.info(f"Private key: {private_key_path}")
            output.info(f"Public key: {public_key_path}")
            
            return {
                'private_key_path': str(private_key_path),
                'public_key_path': str(public_key_path),
                'private_key': private_key_bytes.decode('utf-8'),
                'public_key': public_key_str
            }
            
        except Exception as e:
            output.error(f"Error generating SSH key for worker {hostname}: {e}")
            raise e
    
    def _cleanup_worker_ssh_keys(self, hostname: str, ssh_user: str) -> bool:
        """Clean up SSH keys for a worker.
        
        Args:
            hostname: Worker hostname
            ssh_user: SSH username
            
        Returns:
            True if cleanup successful, False if keys didn't exist
        """
        try:
            # Extract short hostname (remove domain component)
            short_hostname = hostname.split('.')[0]
            
            # Create key identifier: short-hostname-username
            key_id = f"{short_hostname}-{ssh_user}"
            
            # Create key file paths in $PREFIX/etc/
            prefix = self._get_prefix()
            ssh_keys_dir = Path(prefix) / "etc" / "ssh_keys"
            
            private_key_path = ssh_keys_dir / f"{key_id}.id"
            public_key_path = ssh_keys_dir / f"{key_id}.pub"
            
            keys_removed = 0
            
            # Remove private key file if it exists
            if private_key_path.exists():
                private_key_path.unlink()
                keys_removed += 1
                output.info(f"Removed private key: {private_key_path}")
            
            # Remove public key file if it exists
            if public_key_path.exists():
                public_key_path.unlink()
                keys_removed += 1
                output.info(f"Removed public key: {public_key_path}")
            
            if keys_removed == 0:
                output.warning(f"No SSH keys found to cleanup for {hostname} (user: {ssh_user})")
                return False
            else:
                output.info(f"Successfully cleaned up {keys_removed} SSH key files for {hostname} (user: {ssh_user})")
                return True
                
        except Exception as e:
            output.error(f"Error cleaning up SSH keys for worker {hostname}: {e}")
            raise e

    def _build_worker_wheel(self) -> str:
        """Build a fresh worker wheel file and return the path"""
        try:
            # Get the worker directory relative to the current backend directory
            current_dir = Path(__file__).parent  # backend directory
            worker_dir = current_dir.parent / "worker"  # ../worker
            
            if not worker_dir.exists():
                raise FileNotFoundError(f"Worker directory not found: {worker_dir}")
            
            # For now, use the existing wheel file (we already built it manually earlier)
            # TODO: Fix the build environment to include setuptools
            dist_dir = worker_dir / "dist"
            wheel_files = list(dist_dir.glob("*.whl"))
            if not wheel_files:
                raise FileNotFoundError("No existing wheel file found. Please build manually first.")
            
            # Get the most recent wheel file
            latest_wheel = max(wheel_files, key=lambda p: p.stat().st_mtime)
            output.info(f"Using existing worker wheel: {latest_wheel.name}")
            
            return str(latest_wheel)
            
        except Exception as e:
            output.error(f"Error finding worker wheel: {e}")
            raise e

    def _deploy_worker_ssh_key(self, hostname: str, ssh_user: str, password: str, public_key: str) -> bool:
        """Deploy worker's SSH public key to authorized_keys on remote host"""
        try:
            output.info(f"Attempting SSH connection to {ssh_user}@{hostname} for key deployment")
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using password authentication for initial setup
            output.debug(f"SSH connection parameters: hostname={hostname}, username={ssh_user}, timeout=30")
            client.connect(
                hostname=hostname,
                username=ssh_user,
                password=password,
                timeout=30,
                look_for_keys=False,
                allow_agent=False
            )
            output.info(f"SSH connection successful to {hostname}")
            
            # Ensure .ssh directory exists with proper permissions
            client.exec_command('mkdir -p ~/.ssh && chmod 700 ~/.ssh')
            
            # Add public key to authorized_keys
            command = f'echo "{public_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
            stdin, stdout, stderr = client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            
            client.close()
            
            if exit_status == 0:
                output.info(f"SSH public key deployed successfully to {hostname}")
                return True
            else:
                error_output = stderr.read().decode()
                output.error(f"Failed to deploy SSH key to {hostname}: {error_output}")
                return False
                
        except paramiko.ssh_exception.AuthenticationException as e:
            output.error(f"SSH authentication failed for {ssh_user}@{hostname}: {e}")
            output.error("Please verify username/password are correct and user can SSH to target host")
            raise Exception(f"SSH authentication failed for {ssh_user}@{hostname}: {e}")
        except paramiko.ssh_exception.NoValidConnectionsError as e:
            output.error(f"Could not connect to {hostname}: {e}")
            output.error("Please verify hostname/IP is reachable and SSH service is running")
            raise Exception(f"Connection failed to {hostname}: {e}")
        except Exception as e:
            output.error(f"Error deploying SSH key to {hostname}: {e}")
            raise e

    def _cleanup_worker_ssh_keys(self, private_key_path: str, public_key_path: str) -> bool:
        """Clean up SSH key files from local filesystem"""
        try:
            import os
            
            # Remove private key file
            if os.path.exists(private_key_path):
                os.remove(private_key_path)
                output.info(f"Removed private key: {private_key_path}")
            
            # Remove public key file  
            if os.path.exists(public_key_path):
                os.remove(public_key_path)
                output.info(f"Removed public key: {public_key_path}")
                
            return True
            
        except Exception as e:
            output.warning(f"Error cleaning up SSH keys: {e}")
            return False

    def _remove_worker_ssh_key(self, hostname: str, ssh_user: str, private_key_path: str) -> bool:
        """Remove worker's SSH public key from authorized_keys on remote host"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using the deployed private key
            client.connect(
                hostname=hostname,
                username=ssh_user,
                key_filename=private_key_path,
                timeout=30
            )
            
            # Use centralized key identifier logic
            key_id = self._get_key_identifier(hostname, ssh_user)
            # Try multiple patterns to clean up keys - both new and legacy formats
            patterns_to_remove = [
                f"dispatcher-worker-{key_id}$",  # Current pattern
                f"dispatcher-worker-.*-{ssh_user}$"  # Any pattern with this ssh_user
            ]
            
            removed_any = False
            for pattern in patterns_to_remove:
                remove_key_cmd = f"sed -i '/{pattern}/d' ~/.ssh/authorized_keys"
                output.info(f"Attempting to remove SSH keys matching pattern: {pattern}")
                stdin, stdout, stderr = client.exec_command(remove_key_cmd)
                exit_status = stdout.channel.recv_exit_status()
                if exit_status == 0:
                    removed_any = True
                    output.info(f"Removed keys matching pattern: {pattern}")
            
            exit_status = 0 if removed_any else 1
            
            client.close()
            
            if exit_status == 0:
                output.info(f"SSH public key removed successfully from {hostname}")
                return True
            else:
                # Non-fatal - key might not exist
                output.warning(f"Could not remove SSH key from {hostname} (may not exist)")
                return True
                
        except Exception as e:
            output.warning(f"Error removing SSH key from {hostname}: {e}")
            return True  # Non-fatal

    def _setup_remote_environment(self, hostname: str, ssh_user: str, private_key_path: str) -> bool:
        """Setup remote environment with PREFIX directory and virtual environment"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using the deployed private key
            client.connect(
                hostname=hostname,
                username=ssh_user,
                key_filename=private_key_path,
                timeout=30
            )
            
            # Get app name for PREFIX
            app_name = info.name  # "dispatcher"
            prefix_path = f"$HOME/{app_name}"
            
            # Create PREFIX directory
            stdin, stdout, stderr = client.exec_command(f'mkdir -p {prefix_path}')
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error_output = stderr.read().decode()
                raise Exception(f"Failed to create PREFIX directory: {error_output}")
            
            # Create virtual environment
            venv_cmd = f'python3 -m venv {prefix_path}/venv'
            stdin, stdout, stderr = client.exec_command(venv_cmd)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error_output = stderr.read().decode()
                raise Exception(f"Failed to create virtual environment: {error_output}")
            
            # Upgrade pip in venv
            pip_cmd = f'{prefix_path}/venv/bin/pip install --upgrade pip'
            stdin, stdout, stderr = client.exec_command(pip_cmd)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                error_output = stderr.read().decode()
                output.warning(f"Failed to upgrade pip: {error_output}")
                # Continue anyway
            
            # Create complete remote directory structure (bin, etc, lib, logs, venv)
            dirs_to_create = [
                f'{prefix_path}/bin',
                f'{prefix_path}/etc',
                f'{prefix_path}/lib', 
                f'{prefix_path}/logs/workers'
            ]
            
            for dir_path in dirs_to_create:
                mkdir_cmd = f'mkdir -p {dir_path}'
                stdin, stdout, stderr = client.exec_command(mkdir_cmd)
                exit_status = stdout.channel.recv_exit_status()
                if exit_status != 0:
                    error_output = stderr.read().decode()
                    output.warning(f"Failed to create directory {dir_path}: {error_output}")
                    # Continue with other directories
            
            client.close()
            output.info(f"Remote environment setup complete on {hostname}")
            return True
            
        except Exception as e:
            output.error(f"Error setting up remote environment on {hostname}: {e}")
            raise e

    def _cleanup_remote_environment(self, hostname: str, ssh_user: str, private_key_path: str) -> bool:
        """Remove remote PREFIX directory and all contents"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using the deployed private key
            client.connect(
                hostname=hostname,
                username=ssh_user,
                key_filename=private_key_path,
                timeout=30
            )
            
            # Get app name for PREFIX
            app_name = info.name  # "dispatcher"
            prefix_path = f"$HOME/{app_name}"
            
            # Remove entire PREFIX directory
            cleanup_cmd = f'rm -rf {prefix_path}'
            stdin, stdout, stderr = client.exec_command(cleanup_cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            client.close()
            
            if exit_status == 0:
                output.info(f"Remote environment cleaned up successfully on {hostname}")
            else:
                # Non-fatal - directory might not exist
                output.warning(f"Could not cleanup remote environment on {hostname} (may not exist)")
            
            return True
                
        except Exception as e:
            output.warning(f"Error cleaning up remote environment on {hostname}: {e}")
            return True  # Non-fatal

    def _install_worker_package(self, hostname: str, ssh_user: str, private_key_path: str, wheel_path: str) -> bool:
        """Install worker package in remote virtual environment"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using the deployed private key
            client.connect(
                hostname=hostname,
                username=ssh_user,
                key_filename=private_key_path,
                timeout=30
            )
            
            # Transfer wheel file to remote /tmp
            wheel_name = Path(wheel_path).name
            remote_wheel_path = f"/tmp/{wheel_name}"
            
            sftp = client.open_sftp()
            sftp.put(wheel_path, remote_wheel_path)
            sftp.close()
            
            # Get app name for PREFIX
            app_name = info.name  # "dispatcher"
            prefix_path = f"$HOME/{app_name}"
            
            # Install wheel in venv
            install_cmd = f'{prefix_path}/venv/bin/pip install {remote_wheel_path}'
            stdin, stdout, stderr = client.exec_command(install_cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                error_output = stderr.read().decode()
                raise Exception(f"Failed to install worker package: {error_output}")
            
            # Verify installation
            verify_cmd = f'{prefix_path}/venv/bin/python -c "import worker_node; print(\\"Worker package installed successfully\\")"'
            stdin, stdout, stderr = client.exec_command(verify_cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                error_output = stderr.read().decode()
                raise Exception(f"Worker package verification failed: {error_output}")
            
            # Cleanup temp wheel file
            client.exec_command(f'rm -f {remote_wheel_path}')
            
            client.close()
            output.info(f"Worker package installed successfully on {hostname}")
            return True
            
        except Exception as e:
            output.error(f"Error installing worker package on {hostname}: {e}")
            raise e

    def _deploy_worker_async(self, deployment_info: Dict[str, Any]) -> None:
        """Deploy worker asynchronously in background thread"""
        worker = deployment_info['worker']
        deployment_id = deployment_info['deployment_id']
        ssh_key_info = deployment_info['ssh_key_info']
        ssh_target = deployment_info['ssh_target']
        ssh_user = deployment_info['ssh_user']
        password = deployment_info['password']
        
        try:
            output.info(f"Starting async remote deployment for worker {worker.name}")
            deployment_status.update_step(deployment_id, "Validating connection parameters...", 1)
            
            # Build fresh worker wheel
            deployment_status.update_step(deployment_id, "Building worker package...", 2)
            wheel_path = self._build_worker_wheel()
            
            # Deploy SSH public key for future connections
            deployment_status.update_step(deployment_id, "Testing SSH connection...", 3)
            public_key_content = ssh_key_info["public_key"]
            self._deploy_worker_ssh_key(ssh_target, ssh_user, password, public_key_content)
            
            # Get private key path for subsequent operations
            private_key_path = ssh_key_info["private_key_path"]
            
            # Setup remote environment
            deployment_status.update_step(deployment_id, "Setting up remote environment...", 4)
            self._setup_remote_environment(ssh_target, ssh_user, private_key_path)
            
            # Install worker package
            deployment_status.update_step(deployment_id, "Installing worker package...", 5)
            self._install_worker_package(ssh_target, ssh_user, private_key_path, wheel_path)
            
            deployment_status.update_step(deployment_id, "Verifying deployment...", 6)
            deployment_status.update_step(deployment_id, "Deployment completed successfully!", 7)
            deployment_status.complete_deployment(deployment_id, True)
            
            # Create database record after successful deployment
            with db.get_session() as session:
                session.add(worker)
                session.commit()
                session.refresh(worker)
                
                # Add to in-memory list
                with self._lock:
                    self._workers.append(worker)
            
            output.info(f"Remote worker {worker.name} deployed successfully to {ssh_target}")
            
        except Exception as e:
            output.error(f"Failed to deploy remote worker {worker.name}: {e}")
            deployment_status.complete_deployment(deployment_id, False, str(e))
            
            # Clean up SSH keys on deployment failure
            if ssh_key_info:
                self._cleanup_worker_ssh_keys(ssh_key_info["private_key_path"], ssh_key_info["public_key_path"])

    def _uninstall_worker_package(self, hostname: str, ssh_user: str, private_key_path: str) -> bool:
        """Uninstall worker package from remote virtual environment"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using the deployed private key
            client.connect(
                hostname=hostname,
                username=ssh_user,
                key_filename=private_key_path,
                timeout=30
            )
            
            # Get app name for PREFIX
            app_name = info.name  # "dispatcher"
            prefix_path = f"$HOME/{app_name}"
            
            # Check if package is installed
            check_cmd = f'{prefix_path}/venv/bin/pip show dispatcher-worker'
            stdin, stdout, stderr = client.exec_command(check_cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status == 0:
                # Package is installed, uninstall it
                uninstall_cmd = f'{prefix_path}/venv/bin/pip uninstall -y dispatcher-worker'
                stdin, stdout, stderr = client.exec_command(uninstall_cmd)
                exit_status = stdout.channel.recv_exit_status()
                
                if exit_status == 0:
                    output.info(f"Worker package uninstalled successfully from {hostname}")
                else:
                    output.warning(f"Failed to uninstall worker package from {hostname}")
            else:
                output.info(f"Worker package not found on {hostname} (already uninstalled)")
            
            client.close()
            return True
            
        except Exception as e:
            output.warning(f"Error uninstalling worker package from {hostname}: {e}")
            return True  # Non-fatal

    def create(
        self,
        name: str,
        worker_type: str = "remote",
        hostname: Optional[str] = None,
        ip_address: Optional[str] = None,
        port: Optional[int] = None,
        ssh_user: Optional[str] = None,
        auth_method: str = "key",
        ssh_private_key: Optional[str] = None,
        password: Optional[str] = None,
        provision: bool = False,
        max_jobs: int = 10
    ) -> WorkerModel:
        """Create a new worker record in the database"""
        with self._lock:
            with db.get_session() as session:
                # Validate worker_type
                valid_types = ["local", "remote"]
                if worker_type not in valid_types:
                    raise ValueError(f"Invalid worker_type: {worker_type}. Must be one of: {valid_types}")
                
                # Validate auth_method
                valid_auth_methods = ["key", "password"]
                if auth_method not in valid_auth_methods:
                    raise ValueError(f"Invalid auth_method: {auth_method}. Must be one of: {valid_auth_methods}")
                
                # Check if worker name already exists
                existing = session.query(WorkerModel).filter_by(name=name).first()
                if existing:
                    raise ValueError(f"Worker with name '{name}' already exists")
                
                # Calculate default port if not provided
                if port is None:
                    max_id = session.query(func.max(WorkerModel.id)).scalar() or 0
                    port = 8500 + max_id + 1
                
                # Set up log file path for the worker (similar to job log paths)
                log_dir = Path(info.prefix) / 'logs' / 'workers'
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file_path = log_dir / f"{name.lower()}.log"
                
                # Generate SSH keys for remote workers
                ssh_key_info = None
                if worker_type == "remote" and hostname and ssh_user:
                    try:
                        ssh_key_info = self._generate_worker_ssh_key(hostname, ssh_user)
                        output.info(f"Generated SSH keys for remote worker {name}")
                    except Exception as e:
                        output.error(f"Failed to generate SSH keys for remote worker {name}: {e}")
                        # For now, just log the error but continue with worker creation
                        # In the future, you might want to fail the worker creation
                
                # Create worker record
                worker = WorkerModel(
                    name=name,
                    worker_type=worker_type,
                    hostname=hostname,
                    ip_address=ip_address,
                    port=port,
                    ssh_user=ssh_user,
                    auth_method=auth_method,
                    ssh_private_key=ssh_private_key,
                    password=password,
                    provision=provision,
                    max_jobs=max_jobs,
                    log_file_path=str(log_file_path),
                    status='offline'
                )
                
                # Deploy remote worker BEFORE creating database record
                # Always use IP address if provided, otherwise validate and resolve hostname
                if ip_address:
                    ssh_target = ip_address
                elif hostname:
                    ssh_target = self._resolve_hostname_to_ip(hostname)
                else:
                    ssh_target = None
                    
                # Create worker record first for non-provisioning or local workers
                if not (provision and worker_type == "remote" and ssh_key_info and ssh_target and ssh_user and password):
                    session.add(worker)
                    session.commit()
                    session.refresh(worker)
                    
                    # Add to in-memory list
                    self._workers.append(worker)
                    output.info(f"Worker created: {name} (type: {worker_type})")
                    return worker
                
                # For remote provisioning, start background deployment
                deployment_id = f"{name}_{int(time.time())}"
                deployment_status.start_deployment(deployment_id, name)
                
                # Store deployment info for background thread
                deployment_info = {
                    'worker': worker,
                    'deployment_id': deployment_id,
                    'ssh_key_info': ssh_key_info,
                    'ssh_target': ssh_target,
                    'ssh_user': ssh_user,
                    'password': password,
                    'session': session  # We'll need a new session in the thread
                }
                
                # Start deployment in background thread
                deployment_thread = Thread(
                    target=self._deploy_worker_async,
                    args=(deployment_info,),
                    daemon=True
                )
                deployment_thread.start()
                
                # Return immediately with deployment_id for polling
                return {
                    'deployment_id': deployment_id,
                    'message': f'Worker deployment started for {name}'
                }
    
    def get_by_id(self, worker_id: int) -> Optional[WorkerModel]:
        """Get worker by ID"""
        with db.get_session() as session:
            return session.query(WorkerModel).filter_by(id=worker_id).first()
    
    def get_by_name(self, name: str) -> Optional[WorkerModel]:
        """Get worker by name"""
        with db.get_session() as session:
            return session.query(WorkerModel).filter_by(name=name).first()
    
    def list_with_count(
        self,
        limit: int = 20,
        offset: int = 0,
        name_filter: Optional[str] = None,
        worker_type_filter: Optional[str] = None,
        status_filter: Optional[str] = None
    ) -> tuple[List[WorkerModel], int]:
        """Get paginated list of workers with total count from in-memory list"""
        with self._lock:
            # Work with a copy of the in-memory workers list
            workers = self._workers.copy()
            
            # Apply filters
            if name_filter:
                workers = [w for w in workers if name_filter.lower() in w.name.lower()]
            if worker_type_filter:
                workers = [w for w in workers if w.worker_type == worker_type_filter]
            if status_filter:
                workers = [w for w in workers if w.status == status_filter]
            
            # Get total count after filtering
            total = len(workers)
            
            # Sort by created_at descending (newest first)
            workers.sort(key=lambda w: w.created_at, reverse=True)
            
            # Apply pagination
            paginated_workers = workers[offset:offset + limit]
            
            # Debug output to see what we're returning
            if paginated_workers:
                output.info(f"DEBUG: Returning worker with status: {paginated_workers[0].status}")
            
            return paginated_workers, total
    
    def update(
        self,
        worker_id: int,
        name: Optional[str] = None,
        worker_type: Optional[str] = None,
        hostname: Optional[str] = None,
        ip_address: Optional[str] = None,
        port: Optional[int] = None,
        ssh_user: Optional[str] = None,
        auth_method: Optional[str] = None,
        ssh_private_key: Optional[str] = None,
        password: Optional[str] = None,
        provision: Optional[bool] = None,
        max_jobs: Optional[int] = None
    ) -> Optional[WorkerModel]:
        """Update worker"""
        with self._lock:
            with db.get_session() as session:
                worker = session.query(WorkerModel).filter_by(id=worker_id).first()
                if not worker:
                    return None
                
                # Validate worker_type if provided
                if worker_type is not None:
                    valid_types = ["local", "remote"]
                    if worker_type not in valid_types:
                        raise ValueError(f"Invalid worker_type: {worker_type}. Must be one of: {valid_types}")
                
                # Validate auth_method if provided
                if auth_method is not None:
                    valid_auth_methods = ["key", "password"]
                    if auth_method not in valid_auth_methods:
                        raise ValueError(f"Invalid auth_method: {auth_method}. Must be one of: {valid_auth_methods}")
                
                # Check name uniqueness if changing name
                if name is not None and name != worker.name:
                    existing = session.query(WorkerModel).filter_by(name=name).first()
                    if existing:
                        raise ValueError(f"Worker with name '{name}' already exists")
                
                # Update fields
                if name is not None:
                    worker.name = name
                if worker_type is not None:
                    worker.worker_type = worker_type
                if hostname is not None:
                    worker.hostname = hostname
                if ip_address is not None:
                    worker.ip_address = ip_address
                if port is not None:
                    worker.port = port
                if ssh_user is not None:
                    worker.ssh_user = ssh_user
                if auth_method is not None:
                    worker.auth_method = auth_method
                if ssh_private_key is not None:
                    worker.ssh_private_key = ssh_private_key
                if password is not None:
                    worker.password = password
                if provision is not None:
                    worker.provision = provision
                if max_jobs is not None:
                    worker.max_jobs = max_jobs
                
                session.commit()
                session.refresh(worker)
                
                # Also update the in-memory worker object
                worker_in_memory = next((w for w in self._workers if w.id == worker_id), None)
                if worker_in_memory:
                    if name is not None:
                        worker_in_memory.name = name
                    if worker_type is not None:
                        worker_in_memory.worker_type = worker_type
                    if hostname is not None:
                        worker_in_memory.hostname = hostname
                    if ip_address is not None:
                        worker_in_memory.ip_address = ip_address
                    if port is not None:
                        worker_in_memory.port = port
                    if ssh_user is not None:
                        worker_in_memory.ssh_user = ssh_user
                    if auth_method is not None:
                        worker_in_memory.auth_method = auth_method
                    if ssh_private_key is not None:
                        worker_in_memory.ssh_private_key = ssh_private_key
                    if password is not None:
                        worker_in_memory.password = password
                    if provision is not None:
                        worker_in_memory.provision = provision
                    if max_jobs is not None:
                        worker_in_memory.max_jobs = max_jobs
                
                # If max_jobs was updated, notify the worker node
                if max_jobs is not None and worker.status == 'online':
                    asyncio.create_task(self._update_worker_config(worker_id, max_jobs))
                
                output.info(f"Worker updated: {worker.name}")
                return worker
    
    def delete(self, worker_id: int) -> bool:
        """Delete worker and clean up associated SSH keys"""
        with self._lock:
            with db.get_session() as session:
                worker = session.query(WorkerModel).filter_by(id=worker_id).first()
                if not worker:
                    return False
                
                # Prevent deletion of system worker
                if worker.name == 'System':
                    raise ValueError("Cannot delete System worker")
                
                # Remote worker cleanup for deployed workers
                if worker.worker_type == "remote" and worker.hostname and worker.ssh_user:
                    try:
                        # Resolve hostname to IP address for SSH connections
                        ssh_target = None
                        if worker.ip_address:
                            # Always use IP address if available
                            ssh_target = worker.ip_address
                            output.info(f"Using IP address {ssh_target} for SSH connections to {worker.hostname}")
                        elif worker.hostname:
                            # Resolve hostname to IP address
                            try:
                                ssh_target = self._resolve_hostname_to_ip(worker.hostname)
                            except Exception as e:
                                output.error(f"Failed to resolve hostname {worker.hostname} for cleanup: {e}")
                                ssh_target = worker.hostname  # Fallback to hostname
                        
                        if not ssh_target:
                            output.error(f"No valid target for SSH connections to worker {worker.name}")
                            raise Exception("No valid SSH target")
                        
                        # Get private key path for remote operations using centralized key logic
                        prefix = self._get_prefix()
                        ssh_keys_dir = Path(prefix) / "etc" / "ssh_keys"
                        
                        # Use centralized key identifier logic
                        key_id = self._get_key_identifier(worker.hostname, worker.ssh_user)
                        private_key_path = ssh_keys_dir / f"{key_id}.id"
                        
                        if private_key_path.exists():
                            output.info(f"Starting remote cleanup for worker {worker.name}")
                            
                            # Uninstall worker package from remote system
                            self._uninstall_worker_package(ssh_target, worker.ssh_user, str(private_key_path))
                            
                            # Cleanup remote environment (PREFIX directory)
                            self._cleanup_remote_environment(ssh_target, worker.ssh_user, str(private_key_path))
                            
                            # Remove SSH key from remote authorized_keys
                            self._remove_worker_ssh_key(ssh_target, worker.ssh_user, str(private_key_path))
                            
                            output.info(f"Remote cleanup completed for worker {worker.name}")
                        
                        # Clean up local SSH keys
                        self._cleanup_worker_ssh_keys(worker.hostname, worker.ssh_user)
                        output.info(f"Cleaned up local SSH keys for worker {worker.name}")
                        
                    except Exception as e:
                        output.error(f"Failed to cleanup worker {worker.name}: {e}")
                        # Continue with worker deletion even if cleanup fails
                
                session.delete(worker)
                session.commit()
                
                # Remove from in-memory list
                self._workers = [w for w in self._workers if w.id != worker_id]
                
                output.info(f"Worker deleted: {worker.name}")
                return True
    
    def update_status(
        self,
        worker_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> Optional[WorkerModel]:
        """Update worker status"""
        with self._lock:
            with db.get_session() as session:
                worker = session.query(WorkerModel).filter_by(id=worker_id).first()
                if not worker:
                    return None
                
                # Validate status
                valid_statuses = ["online", "offline", "provisioning", "error"]
                if status not in valid_statuses:
                    raise ValueError(f"Invalid status: {status}. Must be one of: {valid_statuses}")
                
                worker.status = status
                if error_message is not None:
                    worker.error_message = error_message
                
                session.commit()
                session.refresh(worker)
                
                # Also update the in-memory worker object
                worker_in_memory = next((w for w in self._workers if w.id == worker_id), None)
                if worker_in_memory:
                    worker_in_memory.status = status
                    if error_message is not None:
                        worker_in_memory.error_message = error_message
                
                output.info(f"Worker {worker.name} status updated to {status}")
                return worker
    
    
    def get_available_workers(self) -> List[WorkerModel]:
        """Get all workers that are online and available"""
        with db.get_session() as session:
            return session.query(WorkerModel).filter_by(status='online').all()
    
    def provision_worker(self, worker_id: int) -> bool:
        """Provision a worker (placeholder for future implementation)"""
        with self._lock:
            worker = self.get_by_id(worker_id)
            if not worker:
                return False
            
            if not worker.provision:
                output.warning(f"Worker {worker.name} is not configured for auto-provisioning")
                return False
            
            # TODO: Implement actual provisioning logic
            output.info(f"Provisioning worker {worker.name} (placeholder)")
            
            # Update status to provisioning
            self.update_status(worker_id, 'provisioning')
            
            return True
    
    def _start_local_worker(self, worker_record: WorkerModel) -> bool:
        """Start a local worker process and return success status"""
        try:
            output.info(f"DEBUG: Starting local worker {worker_record.name}...")
            
            # Find the in-memory worker object
            output.info(f"DEBUG: Looking for in-memory worker with ID {worker_record.id}")
            worker_in_memory = next((w for w in self._workers if w.id == worker_record.id), None)
            if not worker_in_memory:
                output.warning(f"Worker {worker_record.id} not found in memory list")
                return False
            
            output.info(f"DEBUG: Found in-memory worker {worker_in_memory.name}")
            
            # Check if process already exists and is running
            output.info(f"DEBUG: Checking if process already exists for {worker_record.name}")
            if hasattr(worker_in_memory, '_process'):
                process = worker_in_memory._process
                if process.poll() is None:
                    output.warning(f"Worker {worker_record.name} process already running (PID: {process.pid})")
                    return True
                else:
                    # Process exists but is dead, remove it
                    output.info(f"DEBUG: Removing dead process attribute for {worker_record.name}")
                    delattr(worker_in_memory, '_process')
            
            # Start the worker process - inline _start_worker_node logic
            output.info(f"DEBUG: Building command for {worker_record.name}")
            backend_url = f"http://{info.get_local_ip()}:{info.port}"
            cmd = [
                "dispatcher-worker",
                "--backend-url", backend_url,
                "--worker-name", worker_record.name,
                "--port", str(worker_record.port),
                "--max-jobs", str(worker_record.max_jobs)
            ]

            output.info(f"DEBUG: Command built: {' '.join(cmd)}")
            output.info(f"DEBUG: Working directory: {info.prefix}")
            output.info(f"DEBUG: PATH environment: {os.environ.get('PATH', 'NOT SET')}")
            
            # Use the log file path from the worker record
            output.info(f"DEBUG: Setting up log file for {worker_record.name}")
            log_file_path = worker_record.log_file_path
            if not log_file_path:
                # Fallback to the old way if path is not set
                log_dir = Path(info.prefix) / 'logs' / 'workers'
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file_path = str(log_dir / f"{worker_record.name.lower()}.log")
            
            output.info(f"DEBUG: Log file path: {log_file_path}")
            
            # Ensure parent directory exists
            output.info(f"DEBUG: Creating log directory if needed")
            Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Start process with proper process group management
            output.info(f"DEBUG: Opening log file for {worker_record.name}")
            def preexec_fn():
                # Make this process the leader of a new process group
                os.setpgrp()
            
            # Open log file for worker output
            log_file = open(log_file_path, 'a', encoding='utf-8')

            # Prepare environment with Redis password
            worker_env = os.environ.copy()
            redis_password_file = Path(info.prefix) / 'etc' / '.redis_password'
            print("password_file: "+str(redis_password_file))
            if redis_password_file.exists():
                redis_password = redis_password_file.read_text().strip()
                worker_env['REDIS_PASSWORD'] = redis_password
                output.info(f"DEBUG: Added REDIS_PASSWORD to worker environment for {worker_record.name}")

            try:
                output.info(f"DEBUG: About to create subprocess for {worker_record.name}")
                process = subprocess.Popen(
                    cmd,
                    cwd=info.prefix,  # Run from prefix directory to avoid queue.py naming conflict
                    stdout=log_file,
                    stderr=subprocess.STDOUT,  # Merge stderr into stdout
                    text=True,
                    env=worker_env,  # Pass environment with Redis password
                    preexec_fn=preexec_fn  # Set up process group for proper cleanup
                )
                output.info(f"DEBUG: Subprocess created successfully for {worker_record.name} (PID: {process.pid})")
            except FileNotFoundError as e:
                output.error(f"Failed to start worker {worker_record.name}: Command not found - {e}")
                log_file.close()
                return False
            except Exception as e:
                output.error(f"Failed to start worker {worker_record.name}: Unexpected error - {e}")
                log_file.close()
                return False
            
            # Store process in worker object (for local workers only)
            output.info(f"DEBUG: Storing process in worker object for {worker_record.name}")
            worker_in_memory._process = process
            output.info(f"DEBUG: Started worker node {worker_record.name} on port {worker_record.port} (PID: {process.pid})")
            
            # Check if process started successfully
            import time
            output.info(f"DEBUG: Checking if worker process {worker_record.name} started successfully...")
            time.sleep(0.5)
            
            if hasattr(worker_in_memory, '_process'):
                process = worker_in_memory._process
                poll_result = process.poll()
                output.info(f"DEBUG: Process poll result for {worker_record.name}: {poll_result}")
                if poll_result is not None:
                    # Process already exited
                    output.error(f"Worker process {worker_record.name} exited immediately with code {poll_result}")
                    return False
            else:
                output.warning(f"No _process attribute found for worker {worker_record.name}")
                return False
                
            output.info(f"DEBUG: Local worker {worker_record.name} started successfully")
            return True
            
        except Exception as e:
            output.error(f"Failed to start local worker {worker_record.name}: {e}")
            return False
    
    def _start_remote_worker(self, worker_record: WorkerModel) -> bool:
        """Start a remote worker using SSH keys and return success status"""
        try:
            output.info(f"Starting remote worker {worker_record.name} (IP: {worker_record.ip_address}, port: {worker_record.port})")
            
            # Get SSH connection details
            ssh_target = worker_record.ip_address or worker_record.hostname
            if not ssh_target:
                output.error(f"No IP address or hostname configured for remote worker {worker_record.name}")
                return False
            
            ssh_user = worker_record.ssh_user
            if not ssh_user:
                output.error(f"No SSH user configured for remote worker {worker_record.name}")
                return False
            
            # Get private key path using the existing key management logic
            prefix = self._get_prefix()
            ssh_keys_dir = Path(prefix) / "etc" / "ssh_keys"
            key_id = self._get_key_identifier(worker_record.hostname, ssh_user)
            private_key_path = ssh_keys_dir / f"{key_id}.id"
            
            if not private_key_path.exists():
                output.error(f"SSH private key not found for remote worker {worker_record.name}: {private_key_path}")
                return False
            
            # Prepare the dispatcher-worker command to run remotely
            backend_url = f"http://{info.get_local_ip()}:{info.port}"

            # Get Redis password for remote worker
            redis_password_file = Path(info.prefix) / 'etc' / '.redis_password'
            redis_password = ""
            if redis_password_file.exists():
                redis_password = redis_password_file.read_text().strip()

            remote_cmd = [
                f"cd ~/{info.name}",
                "&&",
                ". venv/bin/activate",
                "&&",
                f"REDIS_PASSWORD='{redis_password}'",
                "dispatcher-worker",
                "--backend-url", backend_url,
                "--worker-name", worker_record.name,
                "--port", str(worker_record.port),
                "--max-jobs", str(worker_record.max_jobs),
                "&"
            ]
            
            ssh_command = " ".join(remote_cmd)
            output.info(f"Remote SSH command: {ssh_command}")
            
            # Execute the command via SSH
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using the stored private key
            output.debug(f"Connecting to {ssh_user}@{ssh_target} using key {private_key_path}")
            client.connect(
                hostname=ssh_target,
                username=ssh_user,
                key_filename=str(private_key_path),
                timeout=30
            )
            
            # Execute the start command
            stdin, stdout, stderr = client.exec_command(ssh_command)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                error_output = stderr.read().decode('utf-8')
                output.error(f"Remote worker start failed with exit code {exit_status}: {error_output}")
                client.close()
                return False
            
            output.info(f"Remote worker {worker_record.name} started successfully")
            client.close()
            return True
            
        except Exception as e:
            output.error(f"Failed to start remote worker {worker_record.name}: {e}")
            return False
    
    def start_worker(self, worker_id: int) -> Optional[WorkerModel]:
        """Start a worker (local or remote) and update state based on success"""
        output.info(f"DEBUG: start_worker called for worker_id {worker_id}")
        output.info(f"DEBUG: About to acquire lock in start_worker")
        with self._lock:
            output.info(f"DEBUG: Lock acquired in start_worker")
            output.info(f"DEBUG: About to get database session")
            with db.get_session() as session:
                output.info(f"DEBUG: Database session acquired")
                worker = session.query(WorkerModel).filter_by(id=worker_id).first()
                output.info(f"DEBUG: Database query completed")
                if not worker:
                    output.warning(f"Worker {worker_id} not found in database")
                    return None
                
                output.info(f"DEBUG: Found worker {worker.name} (type: {worker.worker_type})")
                
                # Find the in-memory worker object
                worker_in_memory = next((w for w in self._workers if w.id == worker_id), None)
                if not worker_in_memory:
                    output.warning(f"Worker {worker_id} not found in memory list")
                    return None
                
                # Attempt to start the worker based on its type
                success = False
                if worker.worker_type == 'local':
                    success = self._start_local_worker(worker)
                elif worker.worker_type == 'remote':
                    success = self._start_remote_worker(worker)
                else:
                    output.error(f"Unknown worker type '{worker.worker_type}' for worker {worker.name}")
                    success = False
                
                # Update worker state based on startup success
                if success:
                    output.info(f"Worker {worker.name} started successfully")
                    worker.state = 'started'
                    worker_in_memory.state = 'started'
                else:
                    output.error(f"Failed to start worker {worker.name}")
                    worker.state = 'failed'
                    worker_in_memory.state = 'failed'
                
                session.commit()
                return worker if success else None
    
    def stop_worker(self, worker_id: int) -> Optional[WorkerModel]:
        """Stop a worker (set state to 'stopped' and kill process)"""
        with self._lock:
            with db.get_session() as session:
                worker = session.query(WorkerModel).filter_by(id=worker_id).first()
                if not worker:
                    return None
                
                # Handle local vs remote worker stopping
                worker_in_memory = next((w for w in self._workers if w.id == worker_id), None)
                
                if worker.worker_type == "local":
                    # Kill the local worker process if it's running
                    if worker_in_memory and hasattr(worker_in_memory, '_process'):
                        process = worker_in_memory._process
                        try:
                            process.terminate()  # Try graceful termination first
                            process.wait(timeout=5)  # Wait up to 5 seconds
                        except subprocess.TimeoutExpired:
                            process.kill()  # Force kill if it doesn't terminate gracefully
                            process.wait()
                        except Exception as e:
                            output.warning(f"Error terminating worker process {worker_id}: {e}")
                        
                        # Remove process reference
                        delattr(worker_in_memory, '_process')
                        output.info(f"Worker process {worker.name} (PID: {process.pid}) terminated")
                
                elif worker.worker_type == "remote":
                    # Stop remote worker via SSH
                    try:
                        output.info(f"Stopping remote worker {worker.name} at {worker.ip_address}")
                        
                        # Get SSH connection details (same as in _start_remote_worker)
                        ssh_target = worker.ip_address or worker.hostname
                        ssh_user = worker.ssh_user
                        
                        if not ssh_target or not ssh_user:
                            output.error(f"Missing SSH connection details for remote worker {worker.name}")
                        else:
                            # Get private key path
                            prefix = self._get_prefix()
                            ssh_keys_dir = Path(prefix) / "etc" / "ssh_keys"
                            key_id = self._get_key_identifier(worker.hostname, ssh_user)
                            private_key_path = ssh_keys_dir / f"{key_id}.id"
                            
                            if private_key_path.exists():
                                # SSH command to kill dispatcher-worker processes by name
                                stop_cmd = f"pkill -f 'dispatcher-worker.*--worker-name {worker.name}' || true"
                                
                                # Execute via SSH
                                import paramiko
                                client = paramiko.SSHClient()
                                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                                client.connect(
                                    hostname=ssh_target,
                                    username=ssh_user,
                                    key_filename=str(private_key_path),
                                    timeout=10
                                )
                                
                                stdin, stdout, stderr = client.exec_command(stop_cmd)
                                stdout_text = stdout.read().decode().strip()
                                stderr_text = stderr.read().decode().strip()
                                
                                client.close()
                                
                                if stderr_text:
                                    output.warning(f"Remote worker {worker.name} stop command stderr: {stderr_text}")
                                
                                output.info(f"Remote worker {worker.name} stop command executed")
                            else:
                                output.error(f"SSH private key not found for remote worker {worker.name}: {private_key_path}")
                                
                    except Exception as e:
                        output.error(f"Error stopping remote worker {worker.name}: {e}")
                
                worker.state = 'stopped'
                session.commit()
                session.refresh(worker)
                
                # Also update the in-memory worker object
                if worker_in_memory:
                    worker_in_memory.state = 'stopped'
                
                output.info(f"Worker {worker.name} stopped")
                return worker
    
    def pause_worker(self, worker_id: int) -> Optional[WorkerModel]:
        """Pause a worker (set state to 'paused' but keep status as 'online' - dispatcher checks both)"""
        with self._lock:
            with db.get_session() as session:
                worker = session.query(WorkerModel).filter_by(id=worker_id).first()
                if not worker:
                    return None
                
                worker.state = 'paused'
                # Keep status as 'online' - the dispatcher checks both state AND status
                session.commit()
                session.refresh(worker)
                
                # Also update the in-memory worker object
                worker_in_memory = next((w for w in self._workers if w.id == worker_id), None)
                if worker_in_memory:
                    worker_in_memory.state = 'paused'
                    # Keep status unchanged in memory too
                
                output.info(f"Worker {worker.name} paused")
                return worker

    def resume_worker(self, worker_id: int) -> Optional[WorkerModel]:
        """Resume a paused worker (set state back to started, health monitor will set status to online)"""
        with self._lock:
            with db.get_session() as session:
                worker = session.query(WorkerModel).filter_by(id=worker_id).first()
                if not worker:
                    return None
                
                if worker.state != 'paused':
                    output.warning(f"Worker {worker.name} is not paused (current state: {worker.state})")
                    return worker
                
                # Resume to started state, let health monitor handle status
                worker.state = 'started'
                worker.status = 'offline'  # Health monitor will update to 'online' if worker is healthy
                
                session.commit()
                session.refresh(worker)
                
                # Also update the in-memory worker object
                worker_in_memory = next((w for w in self._workers if w.id == worker_id), None)
                if worker_in_memory:
                    worker_in_memory.state = 'started'
                    worker_in_memory.status = 'offline'
                
                output.info(f"Worker {worker.name} resumed")
                return worker

    def get_worker_statistics(self) -> Dict[str, Any]:
        """Get worker statistics"""
        with db.get_session() as session:
            total = session.query(WorkerModel).count()
            online = session.query(WorkerModel).filter_by(status='online').count()
            offline = session.query(WorkerModel).filter_by(status='offline').count()
            provisioning = session.query(WorkerModel).filter_by(status='provisioning').count()
            error = session.query(WorkerModel).filter_by(status='error').count()
            
            # Worker type breakdown
            local_count = session.query(WorkerModel).filter_by(worker_type='local').count()
            remote_count = session.query(WorkerModel).filter_by(worker_type='remote').count()
            
            return {
                "total_workers": total,
                "online_count": online,
                "offline_count": offline,
                "provisioning_count": provisioning,
                "error_count": error,
                "local_workers": local_count,
                "remote_workers": remote_count,
                "availability_rate": (online / total * 100) if total > 0 else 0
            }

    def get_worker_endpoint(self, worker_id: int) -> str:
        """Get worker HTTP endpoint URL"""
        worker_record = self.get_by_id(worker_id)
        if not worker_record:
            raise ValueError(f"Worker {worker_id} not found")
        
        # Use localhost for local workers, IP address for remote workers
        host = "localhost" if worker_record.worker_type == "local" else worker_record.ip_address
        return f"http://{host}:{worker_record.port}"

    async def execute_command(self, worker_id: int, execution_id: str, command: str, args: List[str] = None) -> bool:
        """Execute command on worker node via HTTP REST"""
        try:
            endpoint = self.get_worker_endpoint(worker_id)
            
            # Base64 encode the command for safe transmission
            command_b64 = base64.b64encode(command.encode('utf-8')).decode('utf-8')
            
            # Base64 encode each argument
            args_b64 = []
            if args:
                for arg in args:
                    args_b64.append(base64.b64encode(str(arg).encode('utf-8')).decode('utf-8'))
            
            payload = {
                "execution_id": execution_id,
                "command": command_b64,
                "args": args_b64
            }
            
            output.info(f"DEBUG: Sending to {endpoint}/execute: {payload}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{endpoint}/execute",
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                output.info(f"Command executed on worker {worker_id}, execution_id {execution_id}, PID: {result.get('pid')}")
                return True
                
        except Exception as e:
            detailed_error = f"Failed to execute command on worker {worker_id}: {e}"
            
            # Try to get response body for more detailed error information
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_body = e.response.text
                    detailed_error += f" | Worker response: {error_body}"
                    output.error(f"Worker response body: {error_body}")
                except:
                    pass
            
            output.error(detailed_error)
            
            # Store detailed error for dispatch process to use
            # This could be improved by returning error details, but for now log them
            return False

    async def get_command_status(self, worker_id: int, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get command status from worker node"""
        try:
            endpoint = self.get_worker_endpoint(worker_id)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{endpoint}/status/{execution_id}")
                response.raise_for_status()
                
                return response.json()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            output.error(f"Failed to get status for execution_id {execution_id} on worker {worker_id}: {e}")
            return None
        except Exception as e:
            output.error(f"Failed to get status for execution_id {execution_id} on worker {worker_id}: {e}")
            return None
    
    async def _update_worker_config(self, worker_id: int, max_jobs: int) -> bool:
        """Update worker node configuration via HTTP"""
        try:
            endpoint = self.get_worker_endpoint(worker_id)
            
            payload = {"max_jobs": max_jobs}
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.put(
                    f"{endpoint}/config",
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                output.info(f"Updated worker {worker_id} config: max_jobs={result['max_jobs']}")
                return True
                
        except Exception as e:
            output.warning(f"Failed to update worker {worker_id} config: {e}")
            return False

    async def cancel_command(self, worker_id: int, execution_id: str) -> bool:
        """Cancel running command on worker node"""
        try:
            endpoint = self.get_worker_endpoint(worker_id)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(f"{endpoint}/execute/{execution_id}")
                response.raise_for_status()
                
                result = response.json()
                output.info(f"Command cancelled on worker {worker_id}, execution_id {execution_id}")
                return result.get("cancelled", False)
                
        except Exception as e:
            output.error(f"Failed to cancel command on worker {worker_id}: {e}")
            return False

    async def health_check(self, worker_id: int) -> Optional[Dict[str, Any]]:
        """Check worker node health"""
        try:
            endpoint = self.get_worker_endpoint(worker_id)
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{endpoint}/health")
                response.raise_for_status()
                
                return response.json()
                
        except Exception as e:
            output.error(f"Health check failed for worker {worker_id}: {e}")
            return None

    def _load_workers_from_database(self):
        """Load all workers from database into memory"""
        try:
            with db.get_session() as session:
                workers = session.query(WorkerModel).all()
                self._workers = [worker for worker in workers]
                output.info(f"Loaded {len(self._workers)} workers into memory")
                for worker in self._workers:
                    output.info(f"DEBUG: Loaded worker {worker.id} with status: {worker.status}")
        except Exception as e:
            output.warning(f"Could not load workers from database during startup: {e}")
            self._workers = []
    
    
    def _start_all_workers(self):
        """Start all workers (local and remote) that should be running (called at startup)"""
        try:
            output.info(f"Found {len(self._workers)} total workers to start")
            
            for worker_record in self._workers:
                try:
                    output.info(f"Starting worker: {worker_record.name} (type: {worker_record.worker_type})")
                    self.start_worker(worker_record.id)
                except Exception as e:
                    output.error(f"Failed to start worker {worker_record.name}: {e}")
                    # Continue with other workers even if one fails
                    
        except Exception as e:
            output.warning(f"Could not start workers during startup: {e}")
            # This is expected on first startup when database tables don't exist yet
    
    def _find_worker_process_pid(self, worker_name: str) -> Optional[int]:
        """Find the PID of a running worker process by searching for dispatcher-worker command with worker name"""
        try:
            import subprocess
            # Use ps to find dispatcher-worker processes
            result = subprocess.run(
                ['ps', 'aux'], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            # Look for dispatcher-worker processes with the specific worker name
            for line in result.stdout.splitlines():
                if 'dispatcher-worker' in line and f'--worker-name {worker_name}' in line:
                    # Extract PID (second column in ps aux output)
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1])
                            output.info(f"Found worker {worker_name} process: PID {pid}")
                            return pid
                        except ValueError:
                            continue
            
            output.info(f"No running process found for worker {worker_name}")
            return None
            
        except Exception as e:
            output.warning(f"Error searching for worker {worker_name} process: {e}")
            return None

    def _start_health_monitor(self):
        """Start the worker health monitoring background thread"""
        if not self._manager_running:
            self._manager_running = True
            self._manager_thread = Thread(target=self._health_monitor_loop, daemon=True)
            self._manager_thread.start()
            output.info("Starting worker health monitoring thread")

    def _health_monitor_loop(self):
        """Main health monitor loop - runs in background thread"""
        output.info("Worker health monitor started")
        
        while self._manager_running:
            try:
                # Check health of all workers from in-memory list
                with self._lock:
                    all_workers = self._workers.copy()  # Make a copy to avoid locking during health checks
                    
                for worker_record in all_workers:
                        if not self._manager_running:
                            break
                        
                        # Check if this is a local worker
                        if worker_record.worker_type == 'local':
                            if hasattr(worker_record, '_process'):
                                # Worker has a process, check if it's still alive
                                process = worker_record._process
                                poll_result = process.poll()
                                
                                if poll_result is not None:
                                    # Process has exited (poll() returns exit code)
                                    output.warning(f"Worker process {worker_record.name} (PID: {process.pid}) exited with code {poll_result}")
                                    
                                    # Clean up process reference
                                    delattr(worker_record, '_process')
                                    
                                    # Update worker state to stopped in database and memory
                                    with db.get_session() as session:
                                        db_worker = session.query(WorkerModel).filter_by(id=worker_record.id).first()
                                        if db_worker:
                                            db_worker.state = 'stopped'
                                            db_worker.status = 'offline'
                                            session.commit()
                                            session.refresh(db_worker)
                                            
                                            # Update in-memory object
                                            worker_record.state = 'stopped'
                                            worker_record.status = 'offline'
                                            
                                            output.info(f"Updated worker {worker_record.name} state to 'stopped' due to process exit")
                                    
                                    # Skip HTTP health check for dead process
                                    continue
                            else:
                                # Local worker has no process attribute - check if it's actually running
                                output.info(f"Local worker {worker_record.name} has no process attribute - checking if process exists")
                                
                                # Check if worker process is actually running by looking for the command
                                running_pid = self._find_worker_process_pid(worker_record.name)
                                if running_pid:
                                    output.info(f"Found running process for worker {worker_record.name} (PID: {running_pid}) - reattaching")
                                    # We can't reattach to the process object, but we know it's running
                                    # Just continue to HTTP health check
                                else:
                                    # Process is truly not running
                                    output.warning(f"Local worker {worker_record.name} has no process attribute and no running process found - marking as stopped")
                                    
                                    # Update worker state to stopped in database and memory
                                    with db.get_session() as session:
                                        db_worker = session.query(WorkerModel).filter_by(id=worker_record.id).first()
                                        if db_worker:
                                            db_worker.state = 'stopped'
                                            db_worker.status = 'offline'
                                            session.commit()
                                            session.refresh(db_worker)
                                            
                                            # Update in-memory object
                                            worker_record.state = 'stopped'
                                            worker_record.status = 'offline'
                                            
                                            output.info(f"Updated worker {worker_record.name} state to 'stopped' - no process found")
                                    
                                    # Skip HTTP health check for worker with no process
                                    continue
                        
                        # Check worker health via API endpoint
                        health_response = asyncio.run(self.health_check(worker_record.id))
                        
                        output.info(f"DEBUG: Worker {worker_record.id} health check response: {health_response}, current status: {worker_record.status}")
                        
                        if health_response:
                            # Worker is responding, map health endpoint status to database status
                            endpoint_status = health_response.get('status', 'healthy')
                            health_status = 'online' if endpoint_status == 'healthy' else 'offline'
                            if worker_record.status != health_status:
                                output.info(f"DEBUG: Updating worker {worker_record.id} status from {worker_record.status} to {health_status}")
                                self.update_status(worker_record.id, health_status)
                        else:
                            # Worker is not responding
                            output.info(f"DEBUG: Worker {worker_record.id} not responding, current status: {worker_record.status}")
                            output.info(f"DEBUG: Checking if '{worker_record.status}' != 'offline': {worker_record.status != 'offline'}")
                            if worker_record.status != 'offline':
                                output.info(f"DEBUG: Setting worker {worker_record.id} to offline")
                                self.update_status(worker_record.id, 'offline')
                            else:
                                output.info(f"DEBUG: Worker {worker_record.id} already offline, no update needed")
                
                # Sleep between health checks
                if self._manager_running:
                    time.sleep(self._monitoring_interval)  # Use configurable monitoring interval
                    
            except Exception as e:
                output.error(f"Error in worker health monitor: {e}")
                time.sleep(10.0)  # Wait longer on error
        
        # Health monitor stopped - no process cleanup needed
        
        output.info("Worker health monitor stopped")


    def shutdown(self):
        """Shutdown worker manager and stop all worker processes"""
        with self._lock:
            # First, terminate all running worker processes
            running_processes = [w for w in self._workers if hasattr(w, '_process')]
            if running_processes:
                output.info(f"Terminating {len(running_processes)} worker processes with process references...")
                for worker in running_processes:
                    try:
                        process = worker._process
                        output.info(f"Terminating worker process {worker.id} (PID: {process.pid})")
                        # Since we used setpgrp(), we need to kill the process group
                        try:
                            # Kill the process group (negative PID)
                            os.killpg(process.pid, signal.SIGTERM)
                            process.wait(timeout=5)  # Wait up to 5 seconds
                        except subprocess.TimeoutExpired:
                            output.warning(f"Worker process {worker.id} did not terminate gracefully, force killing...")
                            try:
                                os.killpg(process.pid, signal.SIGKILL)  # Force kill the process group
                            except ProcessLookupError:
                                # Process group already gone
                                pass
                            process.wait()  # Wait for the kill to complete
                        except ProcessLookupError:
                            # Process already gone
                            output.info(f"Worker process {worker.id} already terminated")
                        else:
                            output.info(f"Worker process {worker.id} terminated")
                        
                        # Remove process reference
                        delattr(worker, '_process')
                    except Exception as e:
                        output.error(f"Failed to terminate worker process {worker.id}: {e}")
            
            # Also kill any dispatcher-worker processes that might be running without process references
            try:
                output.info("Checking for any remaining dispatcher-worker processes...")
                # Find all dispatcher-worker processes
                result = subprocess.run(['pgrep', '-f', 'dispatcher-worker'], capture_output=True, text=True)
                if result.returncode == 0:
                    pids = result.stdout.strip().split('\n')
                    pids = [pid.strip() for pid in pids if pid.strip()]
                    if pids:
                        output.info(f"Found {len(pids)} remaining dispatcher-worker processes: {pids}")
                        for pid in pids:
                            try:
                                output.info(f"Terminating dispatcher-worker process PID {pid}")
                                os.kill(int(pid), signal.SIGTERM)
                            except (ProcessLookupError, ValueError):
                                # Process already gone or invalid PID
                                pass
                        
                        # Wait a moment for graceful shutdown
                        time.sleep(2)
                        
                        # Force kill any that are still running
                        result = subprocess.run(['pgrep', '-f', 'dispatcher-worker'], capture_output=True, text=True)
                        if result.returncode == 0:
                            remaining_pids = result.stdout.strip().split('\n')
                            remaining_pids = [pid.strip() for pid in remaining_pids if pid.strip()]
                            if remaining_pids:
                                output.warning(f"Force killing {len(remaining_pids)} remaining dispatcher-worker processes")
                                for pid in remaining_pids:
                                    try:
                                        os.kill(int(pid), signal.SIGKILL)
                                    except (ProcessLookupError, ValueError):
                                        pass
                else:
                    output.info("No remaining dispatcher-worker processes found")
            except Exception as e:
                output.error(f"Error cleaning up remaining dispatcher-worker processes: {e}")
            
            # Then stop the manager thread
            if self._manager_running:
                self._manager_running = False
                if self._manager_thread and self._manager_thread.is_alive():
                    output.info("Stopping worker node manager thread...")
                    self._manager_thread.join(timeout=10)
                    if self._manager_thread.is_alive():
                        output.warning("Worker node manager thread did not stop gracefully")
                    else:
                        output.info("Worker node manager thread stopped")
                        
            self._initialized = False

    def get_log_file_path(self, worker_id: int) -> Optional[str]:
        """Get the log file path for a worker from database"""
        try:
            worker_record = self.get_by_id(worker_id)
            if not worker_record:
                return None
            return worker_record.log_file_path
        except Exception as e:
            output.error(f"Error getting log file path for worker {worker_id}: {e}")
            return None


# Create singleton instance
worker = Worker()
