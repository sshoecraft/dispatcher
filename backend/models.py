from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, func, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from output import output
from typing import Optional, Dict, Any
import os

# Create a base class for declarative models
Base = declarative_base()

# Dynamically set schema based on environment variables
def get_table_args():
    """
    Get table arguments including schema for PostgreSQL.
    Falls back to no schema (default) for SQLite or if no schema is specified.
    """
    try:
        # Try to get schema from environment variable
        schema = os.getenv('PG_SCHEMA', 'public')
        
        # Only use schema if it's not 'public' (default schema) and not empty
        if schema and schema != 'public':
            return {'schema': schema}
        else:
            return {}  # Use default schema
    except:
        # Fallback to no schema if there's any error
        return {}

class Job(Base):
    __tablename__ = 'jobs'
    __table_args__ = get_table_args()
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing PK - This is the master job ID
    name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default='PENDING')  # PENDING, RUNNING, SUCCESS, FAILURE, REVOKED
    progress = Column(Integer, default=0)  # 0-100
    created_by = Column(String(50))
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    parameters = Column(JSON)  # Input parameters
    result = Column(JSON)  # Task result
    error_message = Column(Text)  # Error details if failed
    log_file_path = Column(String(500))  # Path to individual job log file
 
    worker_name = Column(String(255))  # Worker that processed the task
    queue_name = Column(String(255))  # Queue the job was/is assigned to
    assigned_worker_name = Column(String(255))  # Worker assigned to process this job
    retries = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    eta = Column(DateTime)  # Estimated time of arrival (for scheduled tasks)
    expires = Column(DateTime)  # Task expiration time
    
    def to_dict(self):
        from datetime import timezone
        
        def format_datetime(dt):
            """Convert naive datetime to UTC ISO format with Z suffix."""
            if dt is None:
                return None
            # Assume naive datetimes from PostgreSQL func.now() are UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'progress': self.progress,
            'created_by': self.created_by,
            'created_at': format_datetime(self.created_at),
            'started_at': format_datetime(self.started_at),
            'completed_at': format_datetime(self.completed_at),
            'parameters': self.parameters,
            'result': self.result,
            'error_message': self.error_message,
            'log_file_path': self.log_file_path,
            'worker_name': self.worker_name,
            'queue_name': self.queue_name,
            'assigned_worker_name': self.assigned_worker_name,
            'retries': self.retries,
            'max_retries': self.max_retries,
            'eta': format_datetime(self.eta),
            'expires': format_datetime(self.expires),
            'duration': self._calculate_duration()
        }
    
    def _calculate_duration(self):
        """Calculate task duration in seconds if completed."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds()
        return None


class JobSpec(Base):
    __tablename__ = 'specs'
    __table_args__ = get_table_args()
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)  # Unique job specification name
    description = Column(Text)
    command = Column(Text, nullable=False)  # Command to execute
    created_by = Column(String(50))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)  # Can be disabled without deletion
    
    def to_dict(self):
        from datetime import timezone
        
        def format_datetime(dt):
            """Convert naive datetime to UTC ISO format with Z suffix."""
            if dt is None:
                return None
            # Assume naive datetimes from PostgreSQL func.now() are UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        
        return {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'command': self.command,
            'created_by': self.created_by,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at),
            'is_active': self.is_active
        }


class Worker(Base):
    """
    Worker node configuration model.
    Stores configuration for both local and remote worker nodes.
    """
    __tablename__ = "workers"
    __table_args__ = get_table_args()

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)  # Worker name (e.g., "System", "Node-01")
    worker_type = Column(String(20), nullable=False, default='remote')  # 'local' or 'remote'
    hostname = Column(String(255), nullable=True)  # For remote workers
    ip_address = Column(String(45), nullable=True)  # For remote workers (IPv4/IPv6)
    port = Column(Integer, nullable=False, default=8500)  # HTTP server port for worker node
    ssh_user = Column(String(100), nullable=True, default='')  # SSH username for remote workers
    auth_method = Column(String(20), nullable=True, default='key')  # 'key' or 'password'
    ssh_private_key = Column(Text, nullable=True)  # SSH private key content
    password = Column(String(255), nullable=True)  # SSH password (encrypted)
    provision = Column(Boolean, default=False)  # Whether to auto-provision
    max_jobs = Column(Integer, default=10)  # Maximum concurrent jobs/processes
    log_file_path = Column(String(500))  # Path to worker log file
    status = Column(String(50), default='offline')  # 'online', 'offline', 'provisioning', 'error'
    state = Column(String(20), default='stopped')  # Worker state: 'started', 'stopped', 'paused'
    last_seen = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)  # Last error message
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self, include_backend_status: bool = True) -> Dict[str, Any]:
        """Convert to dictionary, masking sensitive values"""
        from datetime import timezone
        
        def format_datetime(dt):
            """Convert naive datetime to UTC ISO format with Z suffix."""
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        
        # Use the worker's actual status
        computed_status = self.status
        last_seen_display = 'backend-managed'
        
        return {
            'id': self.id,
            'name': self.name,
            'worker_type': self.worker_type,
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'port': self.port,
            'ssh_user': self.ssh_user,
            'auth_method': self.auth_method,
            'ssh_private_key': '***masked***' if self.ssh_private_key else None,
            'password': '***masked***' if self.password else None,
            'provision': self.provision,
            'max_jobs': self.max_jobs,
            'log_file_path': self.log_file_path,
            'status': computed_status,
            'state': self.state,
            'last_seen': last_seen_display,
            'error_message': self.error_message,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at)
        }

    @classmethod
    def create_system_worker(cls):
        """Create the default System worker configuration"""
        return cls(
            name='System',
            worker_type='local',
            hostname='localhost',
            ip_address='127.0.0.1',
            ssh_user=None,
            auth_method=None,
            ssh_private_key=None,
            password=None,
            provision=False,
            max_jobs=4,  # Fixed at 4 processes as requested
            status='offline',
            state='stopped'
        )


class Queue(Base):
    """
    Queue configuration model for database storage.
    Provides database-backed queue management.
    """
    __tablename__ = "queues"
    __table_args__ = get_table_args()

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)  # Queue name (e.g., "system", "Serv")
    state = Column(String(20), default='stopped')  # Queue state: 'started', 'stopped', 'paused'
    time_limit = Column(Integer, default=1200)  # Task time limit in seconds
    priority = Column(String(20), default='normal')  # Priority level: 'critical', 'high', 'normal', 'low'
    strategy = Column(String(50), default='round_robin')  # Dispatch strategy
    description = Column(Text, nullable=True)  # Human-readable description
    log_file_path = Column(String(500))  # Path to queue log file
    is_default = Column(Boolean, default=False)  # Whether this is the default queue
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        from datetime import timezone
        
        def format_datetime(dt):
            """Convert naive datetime to UTC ISO format with Z suffix."""
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'timeLimit': self.time_limit,  # Keep original camelCase for API compatibility
            'priority': self.priority,
            'strategy': self.strategy,
            'description': self.description,
            'log_file_path': self.log_file_path,
            'is_default': self.is_default,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at)
        }


class QWorker(Base):
    """
    Queue-Worker assignment table.
    Many-to-many relationship between queues and workers.
    """
    __tablename__ = "queue_workers"
    __table_args__ = get_table_args()

    id = Column(Integer, primary_key=True, index=True)
    queue_id = Column(Integer, ForeignKey('queues.id', ondelete='CASCADE'), nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey('workers.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    
    # Ensure unique queue-worker combinations
    __table_args__ = (UniqueConstraint('queue_id', 'worker_id', name='_queue_worker_uc'), get_table_args())


    
    # Relationships
    queue = relationship("Queue", backref="queue_workers")
    worker = relationship("Worker", backref="worker_queues")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        from datetime import timezone
        
        def format_datetime(dt):
            """Convert naive datetime to UTC ISO format with Z suffix."""
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        
        return {
            'id': self.id,
            'queue_id': self.queue_id,
            'worker_id': self.worker_id,
            'created_at': format_datetime(self.created_at)
        }


class User(Base):
    """
    User model for authentication and authorization.
    Supports multiple authentication sources (local, OS, LDAP).
    """
    __tablename__ = "users"
    __table_args__ = get_table_args()

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)  # Only for local auth
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default='viewer')  # admin, operator, viewer, auditor
    auth_source = Column(String(20), nullable=False, default='local')  # local, os, ldap
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, optionally including sensitive data"""
        from datetime import timezone
        
        def format_datetime(dt):
            """Convert naive datetime to UTC ISO format with Z suffix."""
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        
        result = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'auth_source': self.auth_source,
            'is_active': self.is_active,
            'last_login': format_datetime(self.last_login),
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at)
        }
        
        if include_sensitive:
            result['password_hash'] = self.password_hash
            
        return result


class UserRole(Base):
    """
    Role definitions for user permissions.
    """
    __tablename__ = "user_roles"
    __table_args__ = get_table_args()

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    permissions = Column(JSON, nullable=True)  # JSON array of permission strings
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        from datetime import timezone
        
        def format_datetime(dt):
            """Convert naive datetime to UTC ISO format with Z suffix."""
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'permissions': self.permissions or [],
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at)
        }


class UserSession(Base):
    """
    User session tracking for JWT tokens.
    """
    __tablename__ = "user_sessions"
    __table_args__ = get_table_args()

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token = Column(String(500), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationship
    user = relationship("User", backref="sessions")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        from datetime import timezone
        
        def format_datetime(dt):
            """Convert naive datetime to UTC ISO format with Z suffix."""
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        
        return {
            'id': self.id,
            'user_id': self.user_id,
            'token': self.token,
            'expires_at': format_datetime(self.expires_at),
            'created_at': format_datetime(self.created_at)
        }