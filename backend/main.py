#!/usr/bin/env python3

import sys
import os
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, Query, Depends, Request
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, Dict, Any, List
import json
import asyncio
import time
from contextlib import asynccontextmanager
from info import info
from output import output, log_config
from db import db, DatabaseConfigUpdateRequest
from job import job
from logger import logger
from specs import specs, SpecCreateRequest, SpecUpdateRequest
from queues import queue, QueueCreateRequest, QueueUpdateRequest
from worker import worker, WorkerCreateRequest, WorkerUpdateRequest
from auth import auth, LoginRequest, TokenResponse, UserCreateRequest, UserUpdateRequest, get_current_user, require_role, require_permission
from models import User, UserRole, UserSession

class JobRunRequest(BaseModel):
    spec_name: Optional[str] = Field(None, description="Job specification name")
    name: Optional[str] = Field(None, description="Job specification name (alternative to spec_name)")
    runtime_args: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Runtime arguments for the job")
    args: Optional[Dict[str, Any]] = Field(None, description="Runtime arguments for the job (alternative to runtime_args)")
    created_by: Optional[str] = Field(default="system", description="User who is running the job")
    queue: Optional[str] = Field(default=None, description="Target queue name (optional)")
    
    def get_spec_name(self) -> str:
        """Get the specification name, preferring spec_name over name."""
        if self.spec_name:
            return self.spec_name
        elif self.name:
            return self.name
        else:
            raise ValueError("Either 'spec_name' or 'name' must be provided")
            
    def get_runtime_args(self) -> Dict[str, Any]:
        """Get the runtime arguments, preferring runtime_args over args."""
        if self.runtime_args:
            return self.runtime_args
        elif self.args:
            return self.args
        else:
            return {}

class JobStatusRequest(BaseModel):
    execution_id: str = Field(..., description="Execution ID in format 'queue_name:job_id'")
    status: str = Field(..., description="Job status: started, completed, failed")
    exit_code: Optional[int] = Field(None, description="Process exit code (for completed/failed)")
    error: Optional[str] = Field(None, description="Error message (for failed status)")


# New startup/shutdown method for fastapi
@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Handle application startup and shutdown."""

	info.set_prefix()
	
	# Always start logger first (non-database dependent)
	logger.start()
	logger.start_redis_consumer()  # Start Redis consumer thread
	
	try:
		db.open()
		
		# Initialize database tables for authentication
		from models import Base
		Base.metadata.create_all(bind=db.engine)
		
		# Initialize default admin user
		with db.get_session() as session:
			auth.initialize_default_admin(session)
		
		job.initialize()
		queue.initialize()
		worker.initialize()
		# specs doesn't need explicit initialization, it uses db sessions on demand
		output.info("Database initialized successfully")
	except Exception as e:
		output.warning(f"Failed to initialize database: {e}")
		output.warning("Starting web server without database connection - database settings can be configured via UI")

	yield

	# Shutdown in reverse order
	output.info("FastAPI lifespan shutdown started...")
	worker.shutdown()
	queue.shutdown()
	logger.stop()
	db.close()
	output.info("FastAPI lifespan shutdown completed")

# App defined here
app = FastAPI(title=info.name, description=info.desc, version=info.version, lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    output.error(f"Validation error for {request.method} {request.url}: {exc.errors()}")
    
    # Clean error details to ensure JSON serializability
    cleaned_errors = []
    for error in exc.errors():
        cleaned_error = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "input": error.get("input")
        }
        # Don't include 'ctx' as it may contain non-serializable objects
        cleaned_errors.append(cleaned_error)
    
    return JSONResponse(
        status_code=422,
        content={"detail": cleaned_errors}
    )

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Accept requests from any origin
    allow_credentials=False,  # Required when using wildcard origins
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Root endpoints
@app.get("/")
def get_root():
    """Root endpoint - API information."""
    return {
        "message": info.name + " API",
        "version": info.version,
        "endpoints": {
            "docs": "/docs",
            "auth": "/api/auth/",
            "users": "/api/users/",
            "db": "/api/db/",
            "jobs": "/api/jobs/",
            "specs": "/api/specs/",
            "queues": "/api/queues/",
            "workers": "/api/workers/"
        }
    }

# Authentication endpoints
@app.post("/api/auth/login", response_model=TokenResponse, tags=["authentication"])
async def login(request: LoginRequest):
    """Authenticate user and return JWT token."""
    try:
        with db.get_session() as session:
            # Authenticate user
            user = auth.authenticate(
                session,
                request.username,
                request.password,
                request.auth_source
            )
            
            if not user:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid username or password"
                )
            
            # Create access token
            access_token = auth.create_access_token(
                data={"sub": user.username, "role": user.role}
            )
            
            # Create session record
            auth.create_user_session(session, user, access_token)
            
            # Return token and user info
            return TokenResponse(
                access_token=access_token,
                user=user.to_dict()
            )
            
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Authentication failed")

@app.post("/api/auth/logout", tags=["authentication"])
async def logout(current_user: User = Depends(get_current_user)):
    """Logout and invalidate token."""
    try:
        with db.get_session() as session:
            # Get token from request
            from fastapi import Request
            from fastapi.security import HTTPBearer
            
            # This is a simplified approach - in production, pass the token properly
            # For now, we'll just clear all sessions for the user
            sessions = session.query(UserSession).filter(
                UserSession.user_id == current_user.id
            ).all()
            
            for user_session in sessions:
                session.delete(user_session)
            
            session.commit()
            
            return {"message": "Successfully logged out"}
            
    except Exception as e:
        output.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")

@app.get("/api/auth/me", tags=["authentication"])
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user information."""
    return current_user.to_dict()

# User management endpoints
@app.post("/api/users", tags=["users"])
async def create_user(
    request: UserCreateRequest,
    current_user: User = Depends(require_role(['admin']))
):
    """Create a new user (admin only)."""
    output.info(f"Creating user: {request.username}, auth_source: {request.auth_source}, role: {request.role}")
    try:
        with db.get_session() as session:
            # Check if username already exists
            existing_user = session.query(User).filter(
                User.username == request.username
            ).first()
            
            if existing_user:
                raise HTTPException(
                    status_code=409,
                    detail="Username already exists"
                )
            
            # Validate OS user if creating OS auth user
            if request.auth_source == 'os':
                os_user_info = auth.validate_os_user(request.username)
                if not os_user_info:
                    raise HTTPException(
                        status_code=400,
                        detail=f"OS user '{request.username}' does not exist on this system"
                    )
                # Use OS info for full name, override any provided values
                full_name = os_user_info['full_name']
                email = None  # OS doesn't provide email, will be empty
            else:
                full_name = request.full_name
                email = request.email
            
            # Create new user
            new_user = User(
                username=request.username,
                email=email,
                full_name=full_name,
                role=request.role,
                auth_source=request.auth_source,
                is_active=True
            )
            
            # Set password if provided (for local auth)
            if request.auth_source == 'local':
                if not request.password or len(request.password.strip()) == 0:
                    raise HTTPException(
                        status_code=422,
                        detail="Password is required for local authentication"
                    )
                new_user.password_hash = auth.hash_password(request.password)
            
            session.add(new_user)
            session.commit()
            
            return {"user": new_user.to_dict()}
            
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users", tags=["users"])
async def get_users(
    page: int = 1,
    per_page: int = 20,
    current_user: User = Depends(get_current_user)
):
    """Get all users with pagination."""
    try:
        with db.get_session() as session:
            offset = (page - 1) * per_page
            
            # Get total count
            total = session.query(User).count()
            
            # Get users
            users = session.query(User).offset(offset).limit(per_page).all()
            
            total_pages = (total + per_page - 1) // per_page
            
            return {
                "users": [user.to_dict() for user in users],
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }
            
    except Exception as e:
        output.error(f"Error getting users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/{user_id}", tags=["users"])
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    """Get a specific user by ID."""
    try:
        with db.get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            return {"user": user.to_dict()}
            
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/users/{user_id}", tags=["users"])
async def update_user(
    user_id: int,
    request: UserUpdateRequest,
    current_user: User = Depends(require_role(['admin']))
):
    """Update a user (admin only)."""
    try:
        with db.get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Update fields if provided
            if request.username is not None:
                # Check if new username already exists
                existing = session.query(User).filter(
                    User.username == request.username,
                    User.id != user_id
                ).first()
                
                if existing:
                    raise HTTPException(
                        status_code=409,
                        detail="Username already exists"
                    )
                
                user.username = request.username
            
            if request.email is not None:
                user.email = request.email
            
            if request.full_name is not None:
                user.full_name = request.full_name
            
            if request.role is not None:
                user.role = request.role
            
            if request.auth_source is not None:
                user.auth_source = request.auth_source
            
            if request.is_active is not None:
                user.is_active = request.is_active
            
            # Update password if provided (for local auth)
            if request.password and user.auth_source == 'local':
                user.password_hash = auth.hash_password(request.password)
            
            session.commit()
            
            return {"user": user.to_dict()}
            
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error updating user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/users/{user_id}", tags=["users"])
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_role(['admin']))
):
    """Delete a user (admin only)."""
    try:
        with db.get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Don't allow deleting the last admin
            if user.role == 'admin':
                admin_count = session.query(User).filter(User.role == 'admin').count()
                if admin_count <= 1:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot delete the last admin user"
                    )
            
            # Delete user sessions
            session.query(UserSession).filter(UserSession.user_id == user_id).delete()
            
            # Delete user
            session.delete(user)
            session.commit()
            
            return {"success": True, "message": "User deleted successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error deleting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 

@app.get("/api/db", tags=["database"])
async def get_db_config():
    """Get database configuration."""
    try:
        config_data = db.get_config()
        return {"configurations": config_data}
    except Exception as e:
        output.error(f"Error getting database config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/db", tags=["database"])
async def put_db_config(request: DatabaseConfigUpdateRequest):
    """Update database configuration."""
    try:
        # Get only non-None values from the request
        updates = {k: v for k, v in request.dict().items() if v is not None}
        
        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        success = db.put_config(updates)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to write database configuration")
            
        return {"success": True, "message": "Database configuration updated successfully"}
        
    except Exception as e:
        output.error(f"Error updating database config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/db/initialize", tags=["database"])
async def initialize_database():
    """Initialize database tables based on configured database type."""
    try:
        # Get database configuration
        db_config = db.get_config().get('database', {})
        db_type = db_config.get('DB_TYPE', {}).get('value', 'postgresql')
        
        output.info(f"Initializing database tables for {db_type}")
        
        # Import models to ensure they're registered with SQLAlchemy
        from models import Job, Worker, Queue
        from sqlalchemy import inspect
        
        # Check if database is open, if not open it
        if not db.opened:
            db.open()
        
        # Get the engine
        engine = db.engine
        if not engine:
            raise HTTPException(status_code=500, detail="Database connection not established")
        
        # Create tables if they don't exist
        from sqlalchemy.ext.declarative import declarative_base
        Base = declarative_base()
        
        # Import all models to register them
        from models import Base as ModelBase
        
        # Create all tables defined in the models
        ModelBase.metadata.create_all(bind=engine)
        
        output.info("Database tables initialized successfully")
        
        # Get list of created tables for confirmation
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        return {
            "success": True, 
            "message": f"Database tables initialized successfully for {db_type}",
            "tables": tables,
            "database_type": db_type
        }
        
    except Exception as e:
        output.error(f"Error initializing database: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs", tags=["jobs"])
async def get_jobs(
    page: int = 1,
    per_page: int = 20,
    exclude_status: Optional[str] = None,
    status_filter: Optional[str] = None,
    user_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: str = 'UTC',
    runtime_args_filter: Optional[str] = None
):
    """Get all jobs from database - fast, simple query.

    Date filters (start_date, end_date) are ISO format strings (e.g., '2025-01-01T00:00:00').
    Timezone specifies how to interpret the dates (default: UTC, server local time).
    runtime_args_filter format: 'key1:value1,key2:value2' (e.g., 'asset_control_id:24,technology_type:Windows')
    """
    try:
        # Parse exclude_status if provided
        exclude_statuses = []
        if exclude_status:
            exclude_statuses = [s.strip() for s in exclude_status.split(',')]

        offset = (page - 1) * per_page
        jobs_list, total = job.list_with_count(
            limit=per_page,
            offset=offset,
            status_filter=status_filter,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            user_filter=user_filter,
            name_filter=name_filter,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
            runtime_args_filter=runtime_args_filter
        )
        
        total_pages = (total + per_page - 1) // per_page
        
        # Simple conversion - queue_name and assigned_worker_name are now in the database
        # Add result_summary field (JSON string version of result) for UI compatibility
        # Also rename error_message to error_summary for UI compatibility
        jobs_data = []
        for job_record in jobs_list:
            job_dict = job_record.to_dict()
            job_dict['result_summary'] = json.dumps(job_record.result) if job_record.result else None
            # Rename error_message to error_summary for UI
            if 'error_message' in job_dict:
                job_dict['error_summary'] = job_dict.pop('error_message')
            jobs_data.append(job_dict)
        
        return {
            "jobs": jobs_data,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }
    except Exception as e:
        output.error(f"Error getting jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jobs/run", tags=["jobs"])
async def run_job(request: JobRunRequest):
    """Run a job from specification - creates job and queues it for execution."""
    try:
        # DEBUG: Log job creation details
        # Get the actual spec name (from either spec_name or name field)
        try:
            actual_spec_name = request.get_spec_name()
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
            
        actual_runtime_args = request.get_runtime_args()
        output.info(f"🚨 DEBUG: /api/jobs/run called with spec_name={actual_spec_name}, created_by={request.created_by}, queue={getattr(request, 'queue', None)}, runtime_args={actual_runtime_args}")
        # TODO: Validate spec exists before creating job
        # spec = specs.get_by_name(request.name)
        # if not spec:
        #     raise HTTPException(status_code=404, detail=f"Job specification '{request.name}' not found")
        
        # Queue integration - determine target queue
        # If no queue specified, use the default queue from database
        if request.queue:
            target_queue = request.queue
        else:
            # Get default queue from database
            default_queue = queue.get_default_queue()
            if not default_queue:
                raise HTTPException(status_code=400, detail="No default queue configured")
            target_queue = default_queue.name
        
        # VALIDATE QUEUE BEFORE CREATING JOB - prevent creation with invalid queues
        try:
            queue_state = queue.check_queue_state(target_queue)
            if queue_state == 'stopped':
                raise HTTPException(
                    status_code=400, 
                    detail=f"Queue '{target_queue}' is stopped and cannot accept new jobs"
                )
            elif queue_state == 'paused':
                output.warning(f"Queue '{target_queue}' is paused, job will be queued but not processed until resumed")
        except ValueError as e:
            # Queue doesn't exist - convert to HTTP exception
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            output.error(f"Error validating queue '{target_queue}': {e}")
            raise HTTPException(status_code=500, detail=f"Queue validation failed: {str(e)}")
        
        # Create the job with validated queue assignment
        created_job = job.create(
            name=actual_spec_name,
            args=actual_runtime_args,
            created_by=request.created_by,
            target_queue=target_queue
        )
        
        # Add job to queue using the queue service (should not fail since queue was validated)
        try:
            queue.add_job(target_queue, created_job.id)
            output.info(f"Job {created_job.id} added to queue '{target_queue}'")
        except Exception as e:
            output.error(f"Failed to add job {created_job.id} to queue '{target_queue}': {e}")
            # Job was created but couldn't be queued - this is a critical error
            raise HTTPException(status_code=500, detail=f"Job created but failed to queue: {str(e)}")
        
        output.info(f"Job {created_job.id} created from spec '{actual_spec_name}'")
        
        return {"job": created_job.to_dict()}
            
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error running job: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/jobs/{job_id}/cancel", tags=["jobs"])
async def cancel_job(job_id: int):
    """Cancel a running job."""
    try:
        with db.get_session() as session:
            success = job.cancel(session, job_id)
            if not success:
                raise HTTPException(status_code=404, detail="Job not found")
            return {"success": True, "message": f"Job {job_id} cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error cancelling job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/jobs/{job_id}", tags=["jobs"])
async def delete_job(job_id: int):
    """Delete a job entry."""
    try:
        with db.get_session() as session:
            success = job.delete(session, job_id)
            if not success:
                raise HTTPException(status_code=404, detail="Job not found")
            return {"success": True, "message": f"Job {job_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error deleting job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/jobs/{job_id}/retry", tags=["jobs"])
async def retry_job(job_id: int, user_id: str = "system"):
    """Retry a failed job."""
    try:
        with db.get_session() as session:
            new_job_id = job.retry(session, job_id, user_id)
            if new_job_id is None:
                raise HTTPException(status_code=400, detail="Job cannot be retried or not found")
            return {"success": True, "new_job_id": new_job_id}
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error retrying job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class MoveJobRequest(BaseModel):
    new_queue: str = Field(..., description="Target queue name")

@app.put("/api/jobs/{job_id}/move", tags=["jobs"])
async def move_job(job_id: int, request: MoveJobRequest):
    """Move a job to a different queue."""
    try:
        # Validate that the target queue exists and is in valid state
        try:
            queue_state = queue.check_queue_state(request.new_queue)
            if queue_state == 'stopped':
                raise HTTPException(status_code=400, detail=f"Queue '{request.new_queue}' is stopped and cannot accept jobs")
        except ValueError as e:
            # Queue doesn't exist - convert to HTTP exception
            raise HTTPException(status_code=400, detail=str(e))
        
        with db.get_session() as session:
            # Check if job exists
            from models import Job
            job_record = session.query(Job).filter_by(id=job_id).first()
            if not job_record:
                raise HTTPException(status_code=404, detail="Job not found")
            
            # Update the job's queue_name in the database immediately
            job_record.queue_name = request.new_queue
            session.commit()
        
        # Add job to the new queue in the queue service
        try:
            queue.add_job(request.new_queue, job_id)
            output.info(f"Job {job_id} moved to queue '{request.new_queue}'")
        except Exception as e:
            # Try to revert the database change if queue operation fails
            with db.get_session() as session:
                job_record = session.query(Job).filter_by(id=job_id).first()
                if job_record:
                    # Try to restore to previous queue (this is best effort)
                    output.error(f"Failed to move job {job_id} to queue '{request.new_queue}': {e}")
            raise HTTPException(status_code=500, detail=f"Failed to move job to queue: {str(e)}")
        
        return {"success": True, "message": f"Job {job_id} moved to queue '{request.new_queue}'"}
            
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error moving job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/statistics/summary", tags=["jobs"])
async def get_job_statistics_summary(days: int = 7):
    """Get job statistics summary."""
    try:
        with db.get_session() as session:
            stats = job.get_statistics(session, days)
            return stats
    except Exception as e:
        output.error(f"Error getting job statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/{job_id}/logs", tags=["jobs"])
async def get_job_logs(job_id: int):
    """Get job logs as plain text."""
    try:
        log_content = job.get_log_content(job_id)
        if log_content is None:
            log_content = f"Error: Unable to retrieve logs for job {job_id}"
        
        # Always return something, even if it's an error message
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=log_content, media_type="text/plain")
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting logs for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/stream", tags=["jobs"])
async def stream_jobs(
    page: int = 1,
    per_page: int = 20,
    exclude_status: Optional[str] = None,
    status_filter: Optional[str] = None,
    user_filter: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone: str = 'UTC'
):
    """Real-time job list stream using Server-Sent Events.

    Date filters (start_date, end_date) are ISO format strings (e.g., '2025-01-01T00:00:00').
    Timezone specifies how to interpret the dates (default: UTC, server local time).
    """
    async def generate_job_stream():
        update_count = 0
        while True:
            try:
                # Parse exclude_status if provided
                exclude_statuses = []
                if exclude_status:
                    exclude_statuses = [s.strip() for s in exclude_status.split(',')]

                offset = (page - 1) * per_page
                jobs_list, total = job.list_with_count(
                    limit=per_page,
                    offset=offset,
                    status_filter=status_filter,
                    exclude_statuses=exclude_statuses if exclude_statuses else None,
                    user_filter=user_filter,
                    start_date=start_date,
                    end_date=end_date,
                    timezone=timezone
                )
                
                total_pages = (total + per_page - 1) // per_page
                
                # Send job update event with simple job data (no expensive queue lookups)
                paginated_jobs = [job_record.to_dict() for job_record in jobs_list]
                
                update_count += 1
                
                # Send job update event
                data = {
                    "jobs": paginated_jobs,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": total_pages,
                    "update_count": update_count
                }
                
                yield f"event: jobs_update\n"
                yield f"data: {json.dumps(data)}\n\n"
                
                # Send heartbeat
                heartbeat_data = {"jobs_count": total, "timestamp": time.time()}
                yield f"event: heartbeat\n"
                yield f"data: {json.dumps(heartbeat_data)}\n\n"
                
                await asyncio.sleep(0.5)  # Update every 500ms for real-time feel
                
            except Exception as e:
                output.error(f"Error in job stream: {e}")
                yield f"event: error\n"
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
    
    return StreamingResponse(
        generate_job_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

@app.get("/api/jobs/realtime", tags=["jobs"])
async def stream_jobs_realtime(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    exclude_status: Optional[str] = Query(None, description="Exclude statuses (comma-separated)"),
    start_date: Optional[str] = Query(None, description="Start date filter (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date filter (ISO format)"),
    timezone: str = Query('UTC', description="Timezone for date interpretation"),
    runtime_args_filter: Optional[str] = Query(None, description="Runtime args filter (key1:value1,key2:value2)")
):
    """Stream job list updates in real-time using Server-Sent Events with 0.5s polling.

    Date filters (start_date, end_date) are ISO format strings (e.g., '2025-01-01T00:00:00').
    Timezone specifies how to interpret the dates (default: UTC, server local time).
    runtime_args_filter format: 'key1:value1,key2:value2' (e.g., 'asset_control_id:24,technology_type:Windows')
    """
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    try:
        async def jobs_stream_generator():
            last_jobs_hash = ""
            update_count = 0
            no_change_count = 0
            first_run = True

            while True:
                try:
                    # Get current jobs using the same logic as the regular jobs endpoint
                    offset = (page - 1) * per_page

                    # Handle exclude_status parameter
                    exclude_statuses = []
                    if exclude_status:
                        exclude_statuses = [s.strip() for s in exclude_status.split(',')]

                    # Get jobs from database
                    jobs_list, total = job.list_with_count(
                        limit=per_page,
                        offset=offset,
                        exclude_statuses=exclude_statuses,
                        start_date=start_date,
                        end_date=end_date,
                        timezone=timezone,
                        runtime_args_filter=runtime_args_filter
                    )
                    
                    # Convert jobs to dict format
                    jobs_data = {
                        "jobs": [j.to_dict() for j in jobs_list],
                        "total": total,
                        "page": page,
                        "per_page": per_page,
                        "total_pages": (total + per_page - 1) // per_page,
                        "update_count": update_count
                    }
                    
                    # Create hash of essential job data to detect changes
                    jobs_hash = json.dumps([
                        {
                            "id": job_data["id"],
                            "status": job_data["status"], 
                            "progress": job_data["progress"],
                            "started_at": job_data.get("started_at"),
                            "completed_at": job_data.get("completed_at")
                        } for job_data in jobs_data["jobs"]
                    ], sort_keys=True)
                    
                    # Send initial data on first run or when data changed
                    if first_run or jobs_hash != last_jobs_hash:
                        if first_run:
                            output.info(f"📡 Real-time: Sending initial SSE data for {len(jobs_data['jobs'])} jobs")
                            first_run = False
                        else:
                            output.info(f"📡 Real-time: Hash changed, sending SSE update for {len(jobs_data['jobs'])} jobs")
                        yield f"event: jobs_update\ndata: {json.dumps(jobs_data)}\n\n"
                        last_jobs_hash = jobs_hash
                        update_count += 1
                        no_change_count = 0
                    else:
                        no_change_count += 1
                        if no_change_count % 10 == 0:  # Log every 5 seconds (10 * 0.5s)
                            output.debug(f"📡 Real-time: No changes detected ({no_change_count} cycles)")
                        
                        # Send heartbeat every 30 seconds even if no changes
                        if update_count == 1:
                            yield f"data: Connected to job list stream\n\n"
                        elif no_change_count % 60 == 0:  # Every 30 seconds
                            yield f"event: heartbeat\ndata: {json.dumps({'timestamp': update_count, 'jobs_count': len(jobs_list)})}\n\n"
                        
                        # Close stream if no changes for 10 minutes and no active jobs
                        if no_change_count > 1200:  # 10 minutes
                            active_jobs = [job_data for job_data in jobs_data["jobs"] if job_data["status"] in ['PENDING', 'RUNNING']]
                            if not active_jobs:
                                yield "event: idle_timeout\ndata: No active jobs, closing stream\n\n"
                                break
                    
                    # Wait before next check (0.5 second intervals for better responsiveness)
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    output.error(f"Error in jobs realtime stream: {e}")
                    yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                    await asyncio.sleep(5)  # Wait longer on error
        
        return StreamingResponse(
            jobs_stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
        
    except Exception as e:
        output.error(f"Error starting real-time jobs stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/{job_id}/logs/stream", tags=["jobs"])
async def stream_job_logs(job_id: int):
    """Real-time job log stream using Server-Sent Events."""
    try:
        # Verify job exists
        with db.get_session() as session:
            job_record = job.get_by_id(session, job_id)
            if not job_record:
                raise HTTPException(status_code=404, detail="Job not found")
        
        async def log_stream_generator():
            # Get log file path from job record (same as static endpoint)
            if not job_record.log_file_path:
                yield f"data: Error: No log file path configured for job {job_id}\n\n"
                return
                
            log_file_path = job_record.log_file_path
            
            if not os.path.exists(log_file_path):
                yield f"data: Error: Log file not found at {log_file_path}\n\n"
                return
            
            # Send initial content
            try:
                with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                    initial_content = f.read()
                    if initial_content:
                        # Send existing content line by line
                        for line in initial_content.splitlines():
                            yield f"data: {line}\n\n"
                    
                    # Get current position for following new content
                    current_pos = f.tell()
                
                # Follow the file like tail -f
                no_update_count = 0
                
                while True:
                    # Check job status (but don't break for completed jobs)
                    with db.get_session() as session:
                        current_job = job.get_by_id(session, job_id)
                        if not current_job:
                            yield "event: error\ndata: Job no longer exists\n\n"
                            break
                    
                    # Check for new content
                    try:
                        with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                            f.seek(current_pos)
                            new_content = f.read()
                            if new_content:
                                for line in new_content.splitlines():
                                    yield f"data: {line}\n\n"
                                current_pos = f.tell()
                                no_update_count = 0
                            else:
                                no_update_count += 1
                    except Exception as e:
                        output.error(f"Error reading log file for job {job_id}: {e}")
                        yield f"data: Error reading log file\n\n"
                        break
                    
                    # Different timeout behavior based on job status
                    heartbeat_interval = 60 if current_job.status in ["Completed", "Failed", "Cancelled"] else 30
                    timeout_limit = 300 if current_job.status in ["Completed", "Failed", "Cancelled"] else 180
                    
                    # If no updates for too long, send heartbeat
                    if no_update_count >= heartbeat_interval:
                        yield f"event: heartbeat\ndata: Job status: {current_job.status}\n\n"
                        no_update_count = 0
                    
                    # Timeout after specified time with no activity
                    if no_update_count >= timeout_limit:
                        yield "event: timeout\ndata: Stream timeout - no activity\n\n"
                        break
                    
                    await asyncio.sleep(1)
                    
            except Exception as e:
                output.error(f"Error opening log file for job {job_id}: {e}")
                yield f"data: Error reading log file: {str(e)}\n\n"
                yield "event: error\ndata: Stream error\n\n"
        
        return StreamingResponse(
            log_stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error starting real-time log stream for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/{job_id}", tags=["jobs"])
async def get_job(job_id: int):
    """Get a single job by ID."""
    try:
        with db.get_session() as session:
            job_record = job.get_by_id(session, job_id)
            if not job_record:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
            return {"job": job_record}
    except Exception as e:
        output.error(f"Error getting job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/specs", tags=["specs"])
async def create_spec(request: SpecCreateRequest):
    """Create a new job specification."""
    try:
        created_spec = specs.create(
            name=request.name,
            description=request.description,
            command=request.command
        )
        
        return {"spec": created_spec.to_dict()}
        
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        output.error(f"Error creating spec: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/specs", tags=["specs"])
async def get_specs(
    page: int = 1,
    per_page: int = 20,
    name_filter: Optional[str] = None
):
    """Get all job specifications with pagination and optional filtering."""
    try:
        offset = (page - 1) * per_page
        
        specs_list, total = specs.list_with_count(
            limit=per_page,
            offset=offset,
            name_filter=name_filter
        )
        
        total_pages = (total + per_page - 1) // per_page
        
        return {
            "specs": [spec.to_dict() for spec in specs_list],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }
        
    except Exception as e:
        output.error(f"Error getting specs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/specs/{spec_id}", tags=["specs"])
async def get_spec(spec_id: int):
    """Get a specific job specification by ID."""
    try:
        spec = specs.get_by_id(spec_id)
        
        if not spec:
            raise HTTPException(status_code=404, detail="Specification not found")
        
        return {"spec": spec.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting spec {spec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/specs/{spec_id}", tags=["specs"])
async def update_spec(spec_id: int, request: SpecUpdateRequest):
    """Update a specific job specification."""
    try:
        updated_spec = specs.update(
            spec_id=spec_id,
            name=request.name,
            description=request.description,
            command=request.command
        )
        
        if not updated_spec:
            raise HTTPException(status_code=404, detail="Specification not found")
        
        return {"spec": updated_spec.to_dict()}
        
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error updating spec {spec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/specs/{spec_id}", tags=["specs"])
async def delete_spec(spec_id: int):
    """Delete a specific job specification (soft delete)."""
    try:
        success = specs.delete(spec_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Specification not found")
        
        return {"success": True, "message": "Specification deleted successfully", "spec_id": spec_id}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error deleting spec {spec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/specs/name/{spec_name}", tags=["specs"])
async def get_spec_by_name(spec_name: str):
    """Get a specific job specification by name."""
    try:
        spec = specs.get_by_name(spec_name)
        
        if not spec:
            raise HTTPException(status_code=404, detail="Specification not found")
        
        return {"spec": spec.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting spec by name '{spec_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queues", tags=["queues"])
async def create_queue(request: QueueCreateRequest):
    """Create a new queue."""
    try:
        created_queue = queue.create(
            name=request.name,
            description=request.description,
            state=request.state,
            time_limit=request.time_limit,
            priority=request.priority,
            strategy=request.strategy,
            is_default=request.is_default
        )
        
        return {"queue": created_queue.to_dict()}
        
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        output.error(f"Error creating queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queues", tags=["queues"])
async def get_queues(
    page: int = 1,
    per_page: int = 20,
    name_filter: Optional[str] = None
):
    """Get all queues with pagination and optional filtering."""
    try:
        offset = (page - 1) * per_page
        
        queues_list, total = queue.list_with_count(
            limit=per_page,
            offset=offset,
            name_filter=name_filter
        )
        
        total_pages = (total + per_page - 1) // per_page
        
        # Add job counts to each queue
        queues_with_counts = []
        for q in queues_list:
            queue_dict = q.to_dict()
            # Get the number of jobs in this queue
            queue_jobs = queue.get_queue_jobs(q.name)
            queue_dict['job_count'] = len(queue_jobs)
            queues_with_counts.append(queue_dict)
        
        return {
            "queues": queues_with_counts,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }
        
    except Exception as e:
        output.error(f"Error getting queues: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queues/realtime", tags=["queues"])
async def stream_queues_realtime(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
):
    """Stream queue list updates in real-time using Server-Sent Events with 0.5s polling."""
    import asyncio
    import json
    from fastapi.responses import StreamingResponse
    
    try:
        async def queues_stream_generator():
            last_queues_hash = ""
            update_count = 0
            no_change_count = 0
            first_run = True
            
            while True:
                try:
                    # Get current queues using the same logic as the regular queues endpoint
                    offset = (page - 1) * per_page
                    
                    queues_list, total = queue.list_with_count(
                        limit=per_page,
                        offset=offset
                    )
                    
                    # Add job counts and worker assignments to each queue
                    queues_with_data = []
                    for q in queues_list:
                        queue_dict = q.to_dict()
                        # Get the number of jobs in this queue
                        queue_jobs = queue.get_queue_jobs(q.name)
                        queue_dict['job_count'] = len(queue_jobs)
                        queues_with_data.append(queue_dict)
                    
                    # Convert queues to response format
                    queues_data = {
                        "queues": queues_with_data,
                        "total": total,
                        "page": page,
                        "per_page": per_page,
                        "total_pages": (total + per_page - 1) // per_page,
                        "update_count": update_count
                    }
                    
                    # Create hash of essential queue data to detect changes
                    queues_hash = json.dumps([
                        {
                            "id": queue_data["id"],
                            "name": queue_data["name"],
                            "state": queue_data["state"],
                            "job_count": queue_data["job_count"]
                        } for queue_data in queues_data["queues"]
                    ], sort_keys=True)
                    
                    # Send initial data on first run or when data changed
                    if first_run or queues_hash != last_queues_hash:
                        if first_run:
                            output.info(f"📡 Real-time: Sending initial SSE data for {len(queues_data['queues'])} queues")
                            first_run = False
                        else:
                            output.info(f"📡 Real-time: Queue data changed, sending SSE update")
                        yield f"event: queues_update\ndata: {json.dumps(queues_data)}\n\n"
                        last_queues_hash = queues_hash
                        update_count += 1
                        no_change_count = 0
                    else:
                        no_change_count += 1
                        if no_change_count % 10 == 0:  # Log every 5 seconds
                            output.debug(f"📡 Real-time queues: No changes detected ({no_change_count} cycles)")
                        
                        # Send connected message only once after initial update
                        if no_change_count == 1 and update_count == 1:
                            yield f"data: Connected to queue list stream\n\n"
                        # Send heartbeat every 30 seconds
                        elif no_change_count % 60 == 0:  # Every 30 seconds
                            yield f"event: heartbeat\ndata: {json.dumps({'timestamp': update_count, 'queues_count': len(queues_list)})}\n\n"
                        
                        # Close stream if no changes for 10 minutes
                        if no_change_count > 1200:  # 10 minutes
                            output.info("📡 Real-time: Closing inactive queue stream")
                            yield f"event: close\ndata: Stream closed due to inactivity\n\n"
                            break
                    
                    await asyncio.sleep(0.5)  # Poll every 500ms
                    
                except Exception as e:
                    output.error(f"Error in queue stream: {e}")
                    yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                    await asyncio.sleep(5)  # Wait longer on error
        
        return StreamingResponse(
            queues_stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
    
    except Exception as e:
        output.error(f"Error setting up queue stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queues/{queue_id}", tags=["queues"])
async def get_queue(queue_id: int):
    """Get a specific queue by ID."""
    try:
        q = queue.get_by_id(queue_id)
        
        if not q:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        return {"queue": q.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/queues/{queue_id}", tags=["queues"])
async def update_queue(queue_id: int, request: QueueUpdateRequest):
    """Update a specific queue."""
    try:
        updated_queue = queue.update(
            queue_id=queue_id,
            name=request.name,
            description=request.description,
            state=request.state,
            time_limit=request.time_limit,
            priority=request.priority,
            strategy=request.strategy,
            is_default=request.is_default
        )
        
        if not updated_queue:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        return {"queue": updated_queue.to_dict()}
        
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error updating queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/queues/{queue_id}", tags=["queues"])
async def delete_queue(queue_id: int):
    """Delete a specific queue."""
    try:
        success = queue.delete(queue_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        return {"success": True, "message": "Queue deleted successfully", "queue_id": queue_id}
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error deleting queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queues/name/{queue_name}", tags=["queues"])
async def get_queue_by_name(queue_name: str):
    """Get a specific queue by name."""
    try:
        q = queue.get_by_name(queue_name)
        
        if not q:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        return {"queue": q.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting queue by name '{queue_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queues/strategies", tags=["queues"])
async def get_available_strategies():
    """Get all available queue strategies."""
    try:
        available_strategies = queue.get_available_strategies()
        return {"strategies": available_strategies}
        
    except Exception as e:
        output.error(f"Error getting available strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queues/{queue_id}/start", tags=["queues"])
async def start_queue(queue_id: int):
    """Start a queue (set state to 'started')."""
    try:
        q = queue.start_queue(queue_id)
        
        if not q:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        return {"success": True, "message": "Queue started successfully", "queue": q.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error starting queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queues/{queue_id}/stop", tags=["queues"])
async def stop_queue(queue_id: int):
    """Stop a queue (set state to 'stopped')."""
    try:
        q = queue.stop_queue(queue_id)
        
        if not q:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        return {"success": True, "message": "Queue stopped successfully", "queue": q.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error stopping queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queues/{queue_id}/pause", tags=["queues"])
async def pause_queue(queue_id: int):
    """Pause a queue (set state to 'paused')."""
    try:
        q = queue.pause_queue(queue_id)
        
        if not q:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        return {"success": True, "message": "Queue paused successfully", "queue": q.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error pausing queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queues/{queue_id}/workers", tags=["queues"])
async def get_queue_workers(queue_id: int):
    """Get all workers assigned to a specific queue."""
    try:
        workers = queue.get_queue_workers(queue_id)
        
        return {
            "success": True,
            "workers": [w.to_dict() for w in workers],
            "count": len(workers)
        }
        
    except Exception as e:
        output.error(f"Error getting workers for queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queues/{queue_id}/available-workers", tags=["queues"])
async def get_available_workers_for_queue(queue_id: int):
    """Get all workers not assigned to a specific queue."""
    try:
        workers = queue.get_available_workers_for_queue(queue_id)
        
        return {
            "success": True,
            "workers": [w.to_dict() for w in workers],
            "count": len(workers)
        }
        
    except Exception as e:
        output.error(f"Error getting available workers for queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class WorkerAssignmentRequest(BaseModel):
    worker_ids: List[int] = Field(..., description="List of worker IDs to assign")

@app.post("/api/queues/{queue_id}/workers/bulk", tags=["queues"])
async def assign_multiple_workers_to_queue(queue_id: int, request: WorkerAssignmentRequest):
    """Assign multiple workers to a queue at once."""
    try:
        success = queue.assign_multiple_workers_to_queue(request.worker_ids, queue_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Queue not found or no workers assigned")
        
        return {"success": True, "message": f"{len(request.worker_ids)} workers assigned to queue successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error assigning multiple workers to queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queues/{queue_id}/workers/{worker_id}", tags=["queues"])
async def assign_worker_to_queue(queue_id: int, worker_id: int):
    """Assign a worker to a queue."""
    try:
        success = queue.assign_worker_to_queue(worker_id, queue_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Queue or worker not found")
        
        return {"success": True, "message": "Worker assigned to queue successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error assigning worker {worker_id} to queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/queues/{queue_id}/workers/{worker_id}", tags=["queues"])
async def unassign_worker_from_queue(queue_id: int, worker_id: int):
    """Unassign a worker from a queue."""
    try:
        success = queue.unassign_worker_from_queue(worker_id, queue_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Queue or worker assignment not found")
        
        return {"success": True, "message": "Worker unassigned from queue successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error unassigning worker {worker_id} from queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queues/{queue_id}/logs", tags=["queues"])
async def get_queue_logs(queue_id: int):
    """Get queue logs as plain text."""
    try:
        log_content = queue.get_log_content(queue_id)
        if log_content is None:
            log_content = f"Error: Unable to retrieve logs for queue {queue_id}"
        
        # Always return something, even if it's an error message
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=log_content, media_type="text/plain")
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting logs for queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queues/{queue_id}/logs/clear", tags=["queues"])
async def clear_queue_logs(queue_id: int):
    """Clear queue logs (truncate log file)."""
    try:
        # Verify queue exists
        queue_record = queue.get_by_id(queue_id)
        if not queue_record:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        success = queue.clear_log_content(queue_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to clear queue logs")
        
        return {"success": True, "message": "Queue logs cleared successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error clearing logs for queue {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/queues/{queue_id}/logs/stream", tags=["queues"])
async def stream_queue_logs(queue_id: int):
    """Stream queue logs in real-time using Server-Sent Events."""
    import asyncio
    from fastapi.responses import StreamingResponse
    from pathlib import Path
    
    try:
        # Verify queue exists
        queue_record = queue.get_by_id(queue_id)
        if not queue_record:
            raise HTTPException(status_code=404, detail="Queue not found")
        
        log_file_path = queue_record.log_file_path
        if not log_file_path or not Path(log_file_path).exists():
            raise HTTPException(status_code=404, detail="Queue log file not found")
        
        async def log_stream_generator():
            last_position = 0
            no_new_data_count = 0
            
            # Send initial connection message
            yield f"event: connected\ndata: Queue logs stream connected\n\n"
            
            while True:
                try:
                    # Read new content from log file
                    with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                        f.seek(last_position)
                        new_content = f.read()
                        current_position = f.tell()
                    
                    if new_content:
                        # Send new log content
                        for line in new_content.splitlines():
                            if line.strip():  # Only send non-empty lines
                                yield f"data: {line}\n\n"
                        last_position = current_position
                        no_new_data_count = 0
                    else:
                        no_new_data_count += 1
                        
                        # Send heartbeat every 30 seconds
                        if no_new_data_count % 60 == 0:  # 60 * 0.5s = 30s
                            yield f"event: heartbeat\ndata: Queue logs monitoring active\n\n"
                        
                        # Timeout after 5 minutes of no new data
                        if no_new_data_count > 600:  # 600 * 0.5s = 5 minutes
                            yield "event: timeout\ndata: No new log data for 5 minutes, closing stream\n\n"
                            break
                    
                    await asyncio.sleep(0.5)  # Check every 500ms
                    
                except FileNotFoundError:
                    yield "event: error\ndata: Log file no longer exists\n\n"
                    break
                except Exception as e:
                    output.error(f"Error streaming queue logs: {e}")
                    yield f"event: error\ndata: {str(e)}\n\n"
                    await asyncio.sleep(5)  # Wait longer on error
        
        return StreamingResponse(
            log_stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error setting up queue log stream for {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workers", tags=["workers"])
async def create_worker(request: WorkerCreateRequest):
    """Create a new worker."""
    try:
        created_result = worker.create(
            name=request.name,
            worker_type=request.worker_type,
            hostname=request.hostname,
            ip_address=request.ip_address,
            ssh_user=request.ssh_user,
            auth_method=request.auth_method,
            ssh_private_key=request.ssh_private_key,
            password=request.password,
            provision=request.provision,
            max_jobs=request.max_jobs
        )
        
        # Handle both Worker model objects and deployment dictionaries
        if isinstance(created_result, dict):
            # This is an async deployment - return deployment info
            return created_result
        else:
            # This is a regular worker creation - return worker info
            result = {"worker": created_result.to_dict()}
            
            # Include deployment_id if this is a remote deployment
            if hasattr(created_result, '_deployment_id'):
                result["deployment_id"] = created_result._deployment_id
                
            return result
        
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        output.error(f"Error creating worker: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/deployment-status/{deployment_id}", tags=["workers"])
async def get_deployment_status(deployment_id: str):
    """Get real-time deployment status for a worker."""
    try:
        from worker import deployment_status
        status = deployment_status.get_status(deployment_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Deployment not found")
        
        return {
            "deployment_id": deployment_id,
            "worker_name": status['worker_name'],
            "current_step": status['current_step'],
            "step_number": status['step_number'],
            "total_steps": status['total_steps'],
            "status": status['status'],
            "started_at": status['started_at'].isoformat(),
            "last_updated": status['last_updated'].isoformat(),
            "error": status.get('error')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting deployment status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers", tags=["workers"])
async def get_workers(
    page: int = 1,
    per_page: int = 20,
    name_filter: Optional[str] = None,
    worker_type_filter: Optional[str] = None,
    status_filter: Optional[str] = None
):
    """Get all workers with pagination and optional filtering."""
    try:
        offset = (page - 1) * per_page
        
        workers_list, total = worker.list_with_count(
            limit=per_page,
            offset=offset,
            name_filter=name_filter,
            worker_type_filter=worker_type_filter,
            status_filter=status_filter
        )
        
        total_pages = (total + per_page - 1) // per_page
        
        # Enhance each worker's data with running jobs count
        enhanced_workers = []
        for w in workers_list:
            worker_dict = w.to_dict()
            # Get current running jobs count for this worker
            try:
                running_jobs_count = queue._get_worker_running_jobs_count(w.name)
                worker_dict['current_jobs'] = running_jobs_count
            except Exception as e:
                output.warning(f"Could not get running jobs count for worker {w.name}: {e}")
                worker_dict['current_jobs'] = 0
            enhanced_workers.append(worker_dict)
        
        return {
            "workers": enhanced_workers,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }
        
    except Exception as e:
        output.error(f"Error getting workers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/statistics", tags=["workers"])
async def get_worker_statistics():
    """Get worker statistics."""
    try:
        stats = worker.get_worker_statistics()
        return {"statistics": stats}
        
    except Exception as e:
        output.error(f"Error getting worker statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/available", tags=["workers"])
async def get_available_workers():
    """Get all available (online) workers."""
    try:
        workers_list = worker.get_available_workers()
        
        return {
            "workers": [w.to_dict() for w in workers_list],
            "count": len(workers_list)
        }
        
    except Exception as e:
        output.error(f"Error getting available workers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/monitoring", tags=["workers"])
async def get_worker_monitoring_settings():
    """Get worker monitoring settings."""
    try:
        # Get current monitoring interval from worker instance
        interval = getattr(worker, '_monitoring_interval', 30)
        return {
            "interval": interval,
            "description": "Worker health monitoring interval in seconds"
        }
    except Exception as e:
        output.error(f"Error getting monitoring settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class MonitoringUpdateRequest(BaseModel):
    interval: int = Field(..., ge=5, le=300, description="Monitoring interval in seconds (5-300)")

@app.put("/api/workers/monitoring", tags=["workers"])
async def update_worker_monitoring_settings(request: MonitoringUpdateRequest):
    """Update worker monitoring settings."""
    try:
        # Update monitoring interval on worker instance
        worker._monitoring_interval = request.interval
        output.info(f"Updated worker monitoring interval to {request.interval} seconds")
        
        return {
            "message": "Monitoring settings updated successfully",
            "interval": request.interval
        }
    except Exception as e:
        output.error(f"Error updating monitoring settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/realtime", tags=["workers"])
async def stream_workers_realtime(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
):
    """Stream worker list updates in real-time using Server-Sent Events with 0.5s polling."""
    import asyncio
    import json
    from fastapi.responses import StreamingResponse
    
    try:
        async def workers_stream_generator():
            last_workers_hash = ""
            update_count = 0
            no_change_count = 0
            first_run = True
            
            while True:
                try:
                    # Get current workers using the same logic as the regular workers endpoint
                    offset = (page - 1) * per_page
                    
                    workers_list, total = worker.list_with_count(
                        limit=per_page,
                        offset=offset
                    )
                    
                    # Enhance each worker's data with running jobs count
                    enhanced_workers = []
                    for w in workers_list:
                        worker_dict = w.to_dict()
                        # Get current running jobs count for this worker
                        try:
                            running_jobs_count = queue._get_worker_running_jobs_count(w.name)
                            worker_dict['current_jobs'] = running_jobs_count
                        except Exception as e:
                            output.debug(f"Could not get running jobs for worker {w.name}: {e}")
                            worker_dict['current_jobs'] = 0
                        enhanced_workers.append(worker_dict)
                    
                    # Convert workers to response format
                    workers_data = {
                        "workers": enhanced_workers,
                        "total": total,
                        "page": page,
                        "per_page": per_page,
                        "total_pages": (total + per_page - 1) // per_page,
                        "update_count": update_count
                    }
                    
                    # Create hash of essential worker data to detect changes
                    workers_hash = json.dumps([
                        {
                            "id": worker_data["id"],
                            "name": worker_data["name"],
                            "status": worker_data["status"],
                            "state": worker_data["state"],
                            "current_jobs": worker_data.get("current_jobs", 0)
                        } for worker_data in workers_data["workers"]
                    ], sort_keys=True)
                    
                    # Send initial data on first run or when data changed
                    if first_run or workers_hash != last_workers_hash:
                        if first_run:
                            output.info(f"📡 Real-time: Sending initial SSE data for {len(workers_data['workers'])} workers")
                            first_run = False
                        else:
                            output.info(f"📡 Real-time: Worker data changed, sending SSE update")
                        yield f"event: workers_update\ndata: {json.dumps(workers_data)}\n\n"
                        last_workers_hash = workers_hash
                        update_count += 1
                        no_change_count = 0
                    else:
                        no_change_count += 1
                        if no_change_count % 10 == 0:  # Log every 5 seconds
                            output.debug(f"📡 Real-time workers: No changes detected ({no_change_count} cycles)")
                        
                        # Send connected message only once after initial update  
                        if no_change_count == 1 and update_count == 1:
                            yield f"data: Connected to worker list stream\n\n"
                        # Send heartbeat every 30 seconds
                        elif no_change_count % 60 == 0:  # Every 30 seconds
                            yield f"event: heartbeat\ndata: {json.dumps({'timestamp': update_count, 'workers_count': len(workers_list)})}\n\n"
                        
                        # Close stream if no changes for 10 minutes
                        if no_change_count > 1200:  # 10 minutes
                            output.info("📡 Real-time: Closing inactive worker stream")
                            yield f"event: close\ndata: Stream closed due to inactivity\n\n"
                            break
                    
                    await asyncio.sleep(0.5)  # Poll every 500ms
                    
                except Exception as e:
                    output.error(f"Error in worker stream: {e}")
                    yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                    await asyncio.sleep(5)  # Wait longer on error
        
        return StreamingResponse(
            workers_stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
    
    except Exception as e:
        output.error(f"Error setting up worker stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/{worker_id}", tags=["workers"])
async def get_worker(worker_id: int):
    """Get a specific worker by ID."""
    try:
        w = worker.get_by_id(worker_id)
        
        if not w:
            raise HTTPException(status_code=404, detail="Worker not found")
        
        return {"worker": w.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/workers/{worker_id}", tags=["workers"])
async def update_worker(worker_id: int, request: WorkerUpdateRequest):
    """Update a specific worker."""
    try:
        updated_worker = worker.update(
            worker_id=worker_id,
            name=request.name,
            worker_type=request.worker_type,
            hostname=request.hostname,
            ip_address=request.ip_address,
            port=request.port,
            ssh_user=request.ssh_user,
            auth_method=request.auth_method,
            ssh_private_key=request.ssh_private_key,
            password=request.password,
            provision=request.provision,
            max_jobs=request.max_jobs
        )
        
        if not updated_worker:
            raise HTTPException(status_code=404, detail="Worker not found")
        
        return {"worker": updated_worker.to_dict()}
        
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error updating worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/workers/{worker_id}", tags=["workers"])
async def delete_worker(worker_id: int):
    """Delete a specific worker."""
    try:
        success = worker.delete(worker_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Worker not found")
        
        return {"success": True, "message": "Worker deleted successfully", "worker_id": worker_id}
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error deleting worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/{worker_id}/logs", tags=["workers"])
async def get_worker_logs(worker_id: int):
    """Get logs for a specific worker."""
    try:
        # Get worker name from database
        worker_record = worker.get_by_id(worker_id)
        if not worker_record:
            raise HTTPException(status_code=404, detail=f"Worker with ID {worker_id} not found")
        
        worker_name = worker_record.name
        
        # Get log content from logger
        log_generator = await logger.get_worker_log_content(worker_name, follow=False)
        
        if log_generator is None:
            return PlainTextResponse(content="", media_type="text/plain")
        
        # Read all content
        log_content = ""
        async for chunk in log_generator:
            log_content += chunk
        
        return PlainTextResponse(content=log_content, media_type="text/plain")
    
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting logs for worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/{worker_id}/logs/stream", tags=["workers"])
async def stream_worker_logs(worker_id: int):
    """Stream logs for a specific worker using Server-Sent Events."""
    try:
        # Get worker name from database
        worker_record = worker.get_by_id(worker_id)
        if not worker_record:
            raise HTTPException(status_code=404, detail=f"Worker with ID {worker_id} not found")
        
        worker_name = worker_record.name
        
        async def generate():
            try:
                # Get log generator with follow=True for streaming
                log_generator = await logger.get_worker_log_content(worker_name, follow=True)
                
                if log_generator is None:
                    # No log file yet, but keep connection open
                    yield f"data: \n\n"
                    # Keep checking for log file creation
                    while True:
                        await asyncio.sleep(1)
                        log_generator = await logger.get_worker_log_content(worker_name, follow=True)
                        if log_generator is not None:
                            break
                        yield f"data: \n\n"  # Send keepalive
                
                # Stream the log content
                async for log_chunk in log_generator:
                    if log_chunk:
                        # Escape the data properly for SSE
                        escaped = log_chunk.replace('\n', '\ndata: ')
                        yield f"data: {escaped}\n\n"
                    else:
                        # Send a keepalive comment
                        yield f": keepalive\n\n"
                    
                    await asyncio.sleep(0.1)  # Small delay between chunks
                    
            except asyncio.CancelledError:
                output.info(f"Worker log stream cancelled for worker {worker_id}")
                raise
            except Exception as e:
                output.error(f"Error in worker log stream: {e}")
                yield f"data: Error: {str(e)}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error streaming logs for worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workers/{worker_id}/logs/clear", tags=["workers"])
async def clear_worker_logs(worker_id: int):
    """Clear logs for a specific worker."""
    try:
        # Get worker name from database
        worker_record = worker.get_by_id(worker_id)
        if not worker_record:
            raise HTTPException(status_code=404, detail=f"Worker with ID {worker_id} not found")
        
        worker_name = worker_record.name
        
        # Clear the log file
        success = await logger.clear_worker_log(worker_name)
        
        if success:
            return {"message": f"Worker {worker_name} logs cleared successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear worker logs")
    
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error clearing logs for worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/name/{worker_name}", tags=["workers"])
async def get_worker_by_name(worker_name: str):
    """Get a specific worker by name."""
    try:
        w = worker.get_by_name(worker_name)
        
        if not w:
            raise HTTPException(status_code=404, detail="Worker not found")
        
        return {"worker": w.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error getting worker by name '{worker_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workers/{worker_id}/provision", tags=["workers"])
async def provision_worker_endpoint(worker_id: int):
    """Provision a worker."""
    try:
        success = worker.provision_worker(worker_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Worker not found or not configured for provisioning")
        
        return {"success": True, "message": "Worker provisioning started"}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error provisioning worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workers/{worker_id}/start", tags=["workers"])
async def start_worker(worker_id: int):
    """Start a worker (set state to 'started')."""
    try:
        success = worker.start_worker(worker_id)
        
        if success is None:
            raise HTTPException(status_code=404, detail="Worker not found")
            
        return {"success": True, "message": "Worker started successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error starting worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workers/{worker_id}/stop", tags=["workers"])
async def stop_worker(worker_id: int):
    """Stop a worker (set state to 'stopped')."""
    try:
        w = worker.stop_worker(worker_id)
        
        if not w:
            raise HTTPException(status_code=404, detail="Worker not found")
        
        return {"success": True, "message": "Worker stopped successfully", "worker": w.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error stopping worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workers/{worker_id}/pause", tags=["workers"])
async def pause_worker(worker_id: int):
    """Pause a worker (set state to 'paused')."""
    try:
        w = worker.pause_worker(worker_id)
        
        if not w:
            raise HTTPException(status_code=404, detail="Worker not found")
        
        return {"success": True, "message": "Worker paused successfully", "worker": w.to_dict()}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error pausing worker {worker_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workers/queue/{queue_name}", tags=["workers"])
async def get_workers_by_queue(queue_name: str):
    """Get all workers assigned to a specific queue."""
    try:
        workers_list = queue.get_queue_workers_by_name(queue_name)
        
        return {
            "workers": [w.to_dict() for w in workers_list],
            "queue_name": queue_name,
            "count": len(workers_list)
        }
        
    except Exception as e:
        output.error(f"Error getting workers for queue '{queue_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))



class LogAppendRequest(BaseModel):
    execution_id: str = Field(..., description="Execution ID in format 'queue_name:job_id'")
    log_data: str = Field(..., description="Log data to append (can be base64 encoded)")
    is_base64: bool = Field(default=False, description="Whether log_data is base64 encoded")

@app.post("/api/node/status", tags=["nodes"])
async def update_job_status(request: JobStatusRequest):
    """Update job status from worker node callback."""
    try:
        # Parse execution_id to extract queue_name and job_id
        try:
            queue_name, job_id_str = request.execution_id.split(':', 1)
            job_id = int(job_id_str)
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail=f"Invalid execution_id format: {request.execution_id}. Expected: queue_name:job_id")
        
        # Update job status based on worker callback
        with db.get_session() as session:
            job_record = job.get_by_id(session, job_id)
            if not job_record:
                raise HTTPException(status_code=404, detail="Job not found")
            
            # Update job status based on worker callback
            if request.status == "started":
                job.update_status(session, job_id, "Running")
            elif request.status == "completed":
                if request.exit_code == 0:
                    # Only set to Completed if job is not already Failed (e.g., from ERROR= in logs)
                    if job_record.status != "Failed":
                        # Set progress to 100% when job completes successfully
                        job.update_status(session, job_id, "Completed", progress=100)
                    else:
                        output.info(f"Job {job_id} already marked as Failed, preserving Failed status")
                    # Remove completed job from queue
                    queue.remove_job(queue_name, job_id)
                    # Close log file handle for completed job
                    await logger.close_log(request.execution_id)
                else:
                    # Also preserve progress for failed jobs
                    current_progress = job_record.progress
                    job.update_status(session, job_id, "Failed", 
                                    progress=current_progress,
                                    error_message=f"Process exited with code {request.exit_code}")
                    # Remove failed job from queue
                    queue.remove_job(queue_name, job_id)
                    # Close log file handle for failed job
                    await logger.close_log(request.execution_id)
            elif request.status == "failed":
                # Check if job already has an error message (from log parsing with ERROR=)
                if job_record.error_message:
                    # Job log ERROR= takes precedence - don't overwrite existing error message
                    output.debug(f"Job {job_id} already has error message from log: {job_record.error_message}")
                    job.update_status(session, job_id, "Failed")
                else:
                    # No existing error, use worker error or default
                    error_msg = request.error or "Worker reported job failure"
                    job.update_status(session, job_id, "Failed", error_message=error_msg)
                # Remove failed job from queue
                queue.remove_job(queue_name, job_id)
                # Close log file handle for failed job
                await logger.close_log(request.execution_id)
            
            return {"success": True, "message": f"Job {job_id} status updated to {request.status}"}
        
    except HTTPException:
        raise
    except Exception as e:
        output.error(f"Error updating job status for execution {execution_id}: {e}")

# WebSocket endpoint removed - replaced by Redis-based logging architecture
# Workers now push logs to Redis queues, backend logger consumes via Redis

if __name__ == "__main__":
	if len(sys.argv) > 1:
		port = int(sys.argv[1])
	else:
		port = info.port

	output.debug(f"port: {port}")
	uvicorn.run(app, host="0.0.0.0", port=port, log_config=log_config)
