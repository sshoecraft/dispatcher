from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from threading import Lock, Thread
from contextlib import contextmanager
import json
import time
import asyncio
import os
from pathlib import Path
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from info import info
from output import output
from db import db
from models import Queue as QueueModel, Worker as WorkerModel, QWorker as QWorkerModel
from strategies import strategies

class QueueCreateRequest(BaseModel):
    name: str = Field(..., description="Queue name")
    description: Optional[str] = Field(None, description="Queue description")
    state: str = Field("stopped", description="Queue state (started, stopped, paused)")
    time_limit: int = Field(1200, description="Task time limit in seconds")
    priority: str = Field("normal", description="Queue priority (critical, high, normal, low)")
    strategy: str = Field("round_robin", description="Dispatch strategy")
    is_default: bool = Field(False, description="Whether this is the default queue")

class QueueUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Queue name")
    description: Optional[str] = Field(None, description="Queue description")
    state: Optional[str] = Field(None, description="Queue state (started, stopped, paused)")
    time_limit: Optional[int] = Field(None, description="Task time limit in seconds")
    priority: Optional[str] = Field(None, description="Queue priority (critical, high, normal, low)")
    strategy: Optional[str] = Field(None, description="Dispatch strategy")
    is_default: Optional[bool] = Field(None, description="Whether this is the default queue")

class Queue:
    def __init__(self):
        self._lock = Lock()
        self._initialized = False
        self._queues = {}  # Dictionary of queue_name -> list of job_ids
        self._dispatcher_running = False
        self._dispatcher_thread = None
    
    def initialize(self):
        """Initialize queue - called at startup"""
        with self._lock:
            if not self._initialized:
                try:
                    # Initialize strategies
                    strategies.initialize()
                    
                    # Restore pending jobs from database to queue lists
                    self._restore_pending_jobs()
                    
                    # Start dispatcher thread
                    self._start_dispatcher()
                    
                    self._initialized = True
                    output.info("Queue initialized successfully")
                except Exception as e:
                    output.error(f"Failed to initialize queue: {e}")
                    raise
    
    def _log_to_queue_file(self, queue_name: str, message: str):
        """Log a message to the specific queue's log file"""
        try:
            # Get the queue to find its log file path
            with db.get_session() as session:
                queue_model = session.query(QueueModel).filter_by(name=queue_name).first()
                if not queue_model or not queue_model.log_file_path:
                    return
                
                log_file_path = queue_model.log_file_path
                
                # Create log directory if it doesn't exist
                os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
                
                # Append message with timestamp
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_entry = f"[{timestamp}] {message}\n"
                
                with open(log_file_path, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
                    
        except Exception as e:
            output.error(f"Error writing to queue log file: {e}")
    
    def _restore_pending_jobs(self):
        """Restore pending jobs from database to queue lists on startup"""
        try:
            from models import Job as JobModel, Queue as QueueModel
            from states import states
            
            with db.get_session() as session:
                # Find the default queue
                default_queue = session.query(QueueModel).filter_by(is_default=True).first()
                if not default_queue:
                    output.warning("No default queue found in database - jobs without queue assignment will not be restored")
                    default_queue_name = None
                else:
                    default_queue_name = default_queue.name
                # Get all jobs that need to be run (not in terminal states)
                terminal_states = states.get_terminal_states()
                output.info(f"Terminal states: {terminal_states}")
                
                # Debug: Check all job statuses
                all_jobs = session.query(JobModel).all()
                status_counts = {}
                for job in all_jobs:
                    status_counts[job.status] = status_counts.get(job.status, 0) + 1
                output.info(f"Job status counts: {status_counts}")
                
                incomplete_jobs = session.query(JobModel).filter(
                    ~JobModel.status.in_(terminal_states)
                ).order_by(JobModel.created_at.asc()).all()
                
                output.info(f"Found {len(incomplete_jobs)} incomplete jobs")
                
                jobs_restored = 0
                jobs_reset = 0
                queues_used = set()
                
                jobs_assigned_queue = 0
                
                for job in incomplete_jobs:
                    queue_name = job.queue_name
                    
                    # Assign missing queue names to default queue (legacy jobs)
                    if not queue_name or queue_name.strip() == '':
                        if default_queue_name:
                            queue_name = default_queue_name
                            job.queue_name = queue_name
                            jobs_assigned_queue += 1
                        else:
                            # Skip jobs without queue assignment if no default queue
                            output.warning(f"Skipping job {job.id} - no queue assigned and no default queue")
                            continue
                        output.info(f"Assigned legacy job {job.id} to default '{queue_name}' queue")
                    
                    # Reset running jobs back to pending (they were interrupted)
                    if job.status == states.RUNNING:
                        job.status = states.PENDING
                        job.started_at = None  # Clear start time
                        job.assigned_worker_name = None  # Clear worker assignment
                        jobs_reset += 1
                        output.info(f"Reset interrupted job {job.id} from {states.RUNNING} to {states.PENDING}")
                    
                    if queue_name not in self._queues:
                        self._queues[queue_name] = []
                    
                    # Add job to the appropriate queue if not already there
                    if job.id not in self._queues[queue_name]:
                        self._queues[queue_name].append(job.id)
                        jobs_restored += 1
                        queues_used.add(queue_name)
                
                # Commit any status changes
                session.commit()
                
                if jobs_restored > 0:
                    reset_msg = f" (reset {jobs_reset} from RUNNING)" if jobs_reset > 0 else ""
                    queue_msg = f" (assigned {jobs_assigned_queue} legacy jobs)" if jobs_assigned_queue > 0 else ""
                    output.info(f"Restored {jobs_restored} incomplete jobs to {len(queues_used)} queue(s): {', '.join(sorted(queues_used))}{reset_msg}{queue_msg}")
                else:
                    output.info("No incomplete jobs found to restore")
                    
        except Exception as e:
            output.error(f"Error restoring pending jobs: {e}")
    
    def shutdown(self):
        """Shutdown queue and stop dispatcher thread"""
        with self._lock:
            if self._dispatcher_running:
                self._dispatcher_running = False
                if self._dispatcher_thread and self._dispatcher_thread.is_alive():
                    output.info("Stopping queue dispatcher thread...")
                    self._dispatcher_thread.join(timeout=5)
                    if self._dispatcher_thread.is_alive():
                        output.warning("Queue dispatcher thread did not stop gracefully")
                    else:
                        output.info("Queue dispatcher thread stopped")
                    
            self._initialized = False
    
    def create(
        self,
        name: str,
        description: Optional[str] = None,
        state: str = "stopped",
        time_limit: int = 1200,
        priority: str = "normal",
        strategy: str = "round_robin",
        is_default: bool = False
    ) -> QueueModel:
        """Create a new queue record in the database"""
        with self._lock:
            with db.get_session() as session:
                # Validate priority
                valid_priorities = ["critical", "high", "normal", "low"]
                if priority not in valid_priorities:
                    raise ValueError(f"Invalid priority: {priority}. Must be one of: {valid_priorities}")
                
                # Validate state
                valid_states = ["started", "stopped", "paused"]
                if state not in valid_states:
                    raise ValueError(f"Invalid state: {state}. Must be one of: {valid_states}")
                
                # Validate strategy
                if not strategies.is_valid_strategy(strategy):
                    raise ValueError(f"Invalid strategy: {strategy}. Must be one of: {strategies.get_all_strategies()}")
                
                # Check if queue name already exists
                existing = session.query(QueueModel).filter_by(name=name).first()
                if existing:
                    raise ValueError(f"Queue with name '{name}' already exists")
                
                # If this queue is being set as default, unset all other defaults
                if is_default:
                    session.query(QueueModel).update({QueueModel.is_default: False})
                    output.info("Unset default flag from all existing queues")
                
                # Set up log file path for the queue (similar to worker and job log paths)
                log_dir = Path(info.prefix) / 'logs' / 'queues'
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file_path = log_dir / f"{name.lower()}.log"
                
                # Create queue record
                queue = QueueModel(
                    name=name,
                    description=description,
                    state=state,
                    time_limit=time_limit,
                    priority=priority,
                    strategy=strategy,
                    log_file_path=str(log_file_path),
                    is_default=is_default
                )
                
                session.add(queue)
                session.commit()
                session.refresh(queue)
                
                output.info(f"Queue created: {name} (priority: {priority})")
                return queue
    
    def get_by_id(self, queue_id: int) -> Optional[QueueModel]:
        """Get queue by ID"""
        with db.get_session() as session:
            return session.query(QueueModel).filter_by(id=queue_id).first()
    
    def get_by_name(self, name: str) -> Optional[QueueModel]:
        """Get queue by name"""
        with db.get_session() as session:
            return session.query(QueueModel).filter_by(name=name).first()
    
    def get_default_queue(self) -> Optional[QueueModel]:
        """Get the default queue"""
        with db.get_session() as session:
            return session.query(QueueModel).filter_by(is_default=True).first()
    
    def list_with_count(
        self,
        limit: int = 20,
        offset: int = 0,
        name_filter: Optional[str] = None
    ) -> tuple[List[QueueModel], int]:
        """Get paginated list of queues with total count"""
        with db.get_session() as session:
            query = session.query(QueueModel)
            
            # Apply filters
            if name_filter:
                query = query.filter(QueueModel.name.ilike(f"%{name_filter}%"))
            
            # Get total count
            total = query.count()
            
            # Apply pagination and ordering
            queues = query.order_by(desc(QueueModel.created_at)).offset(offset).limit(limit).all()
            
            return queues, total
    
    def update(
        self,
        queue_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        state: Optional[str] = None,
        time_limit: Optional[int] = None,
        priority: Optional[str] = None,
        strategy: Optional[str] = None,
        is_default: Optional[bool] = None
    ) -> Optional[QueueModel]:
        """Update queue"""
        with self._lock:
            with db.get_session() as session:
                queue = session.query(QueueModel).filter_by(id=queue_id).first()
                if not queue:
                    return None
                
                # Validate priority if provided
                if priority is not None:
                    valid_priorities = ["critical", "high", "normal", "low"]
                    if priority not in valid_priorities:
                        raise ValueError(f"Invalid priority: {priority}. Must be one of: {valid_priorities}")
                
                # Validate state if provided
                if state is not None:
                    valid_states = ["started", "stopped", "paused"]
                    if state not in valid_states:
                        raise ValueError(f"Invalid state: {state}. Must be one of: {valid_states}")
                
                # Validate strategy if provided
                if strategy is not None:
                    if not strategies.is_valid_strategy(strategy):
                        raise ValueError(f"Invalid strategy: {strategy}. Must be one of: {strategies.get_all_strategies()}")
                
                # Check name uniqueness if changing name
                if name is not None and name != queue.name:
                    existing = session.query(QueueModel).filter_by(name=name).first()
                    if existing:
                        raise ValueError(f"Queue with name '{name}' already exists")
                
                # If this queue is being set as default, unset all other defaults
                if is_default is True:
                    rows_updated = session.query(QueueModel).filter(QueueModel.id != queue_id).update({QueueModel.is_default: False})
                    output.info(f"Unset default flag from {rows_updated} other queue(s)")
                
                # Update fields
                if name is not None:
                    queue.name = name
                if description is not None:
                    queue.description = description
                if state is not None:
                    queue.state = state
                if time_limit is not None:
                    queue.time_limit = time_limit
                if priority is not None:
                    queue.priority = priority
                if strategy is not None:
                    queue.strategy = strategy
                if is_default is not None:
                    queue.is_default = is_default
                
                session.commit()
                session.refresh(queue)
                
                output.info(f"Queue updated: {queue.name}")
                return queue
    
    def delete(self, queue_id: int) -> bool:
        """Delete queue (hard delete since no soft delete field exists)"""
        with self._lock:
            with db.get_session() as session:
                queue = session.query(QueueModel).filter_by(id=queue_id).first()
                if not queue:
                    return False
                
                # Prevent deletion of system queue
                if queue.is_default:
                    raise ValueError("Cannot delete default queue")
                
                # Remove all worker assignments from this queue first
                worker_assignments = session.query(QWorkerModel).filter_by(queue_id=queue_id).all()
                for assignment in worker_assignments:
                    session.delete(assignment)
                
                session.delete(queue)
                session.commit()
                
                output.info(f"Queue deleted: {queue.name} (removed {len(worker_assignments)} worker assignments)")
                return True
    
    def get_available_strategies(self) -> List[Dict[str, str]]:
        """Get all available strategies with descriptions"""
        return [
            {
                "name": strategy,
                "description": strategies.get_strategy_description(strategy)
            }
            for strategy in strategies.get_all_strategies()
        ]
    
    def get_queue_workers(self, queue_id: int) -> List[WorkerModel]:
        """Get all workers assigned to a queue by ID"""
        with db.get_session() as session:
            # Use the QWorkers translation table
            return session.query(WorkerModel)\
                .join(QWorkerModel, WorkerModel.id == QWorkerModel.worker_id)\
                .filter(QWorkerModel.queue_id == queue_id)\
                .all()
    
    def get_queue_workers_by_name(self, queue_name: str) -> List[WorkerModel]:
        """Get all workers assigned to a queue by name"""
        with db.get_session() as session:
            # Get queue first, then get workers
            queue = session.query(QueueModel).filter_by(name=queue_name).first()
            if not queue:
                return []
            
            return session.query(WorkerModel)\
                .join(QWorkerModel, WorkerModel.id == QWorkerModel.worker_id)\
                .filter(QWorkerModel.queue_id == queue.id)\
                .all()
    
    def assign_worker_to_queue(self, worker_id: int, queue_id: int) -> bool:
        """Assign a worker to a queue"""
        with self._lock:
            with db.get_session() as session:
                # Verify queue exists
                queue = session.query(QueueModel).filter_by(id=queue_id).first()
                if not queue:
                    return False
                
                # Verify worker exists
                worker = session.query(WorkerModel).filter_by(id=worker_id).first()
                if not worker:
                    return False
                
                # Check if assignment already exists
                existing = session.query(QWorkerModel)\
                    .filter_by(queue_id=queue_id, worker_id=worker_id)\
                    .first()
                
                if not existing:
                    # Create new assignment
                    assignment = QWorkerModel(
                        queue_id=queue_id,
                        worker_id=worker_id
                    )
                    session.add(assignment)
                    session.commit()
                    
                    output.info(f"Worker {worker_id} assigned to queue {queue.name}")
                
                return True
    
    def unassign_worker_from_queue(self, worker_id: int, queue_id: int) -> bool:
        """Unassign a worker from a specific queue"""
        with self._lock:
            with db.get_session() as session:
                # Get queue name for logging
                queue = session.query(QueueModel).filter_by(id=queue_id).first()
                if not queue:
                    return False
                
                # Remove the assignment
                assignment = session.query(QWorkerModel)\
                    .filter_by(queue_id=queue_id, worker_id=worker_id)\
                    .first()
                
                if assignment:
                    session.delete(assignment)
                    session.commit()
                    
                    output.info(f"Worker {worker_id} unassigned from queue {queue.name}")
                    return True
                
                return False
    
    def get_available_workers_for_queue(self, queue_id: int) -> List[WorkerModel]:
        """Get all workers not currently assigned to a specific queue"""
        with db.get_session() as session:
            # Get all workers
            all_workers = session.query(WorkerModel).all()
            
            # Get workers already assigned to this queue
            assigned_worker_ids = session.query(QWorkerModel.worker_id)\
                .filter_by(queue_id=queue_id)\
                .all()
            assigned_ids = [w[0] for w in assigned_worker_ids]
            
            # Return workers not in assigned list
            return [w for w in all_workers if w.id not in assigned_ids]
    
    def assign_multiple_workers_to_queue(self, worker_ids: List[int], queue_id: int) -> bool:
        """Assign multiple workers to a queue at once"""
        with self._lock:
            with db.get_session() as session:
                # Verify queue exists
                queue = session.query(QueueModel).filter_by(id=queue_id).first()
                if not queue:
                    return False
                
                success_count = 0
                for worker_id in worker_ids:
                    # Verify worker exists
                    worker = session.query(WorkerModel).filter_by(id=worker_id).first()
                    if not worker:
                        continue
                    
                    # Check if assignment already exists
                    existing = session.query(QWorkerModel)\
                        .filter_by(queue_id=queue_id, worker_id=worker_id)\
                        .first()
                    
                    if not existing:
                        # Create new assignment
                        assignment = QWorkerModel(
                            queue_id=queue_id,
                            worker_id=worker_id
                        )
                        session.add(assignment)
                        success_count += 1
                
                session.commit()
                
                if success_count > 0:
                    output.info(f"{success_count} workers assigned to queue {queue.name}")
                
                return success_count > 0

    def start_queue(self, queue_id: int) -> Optional[QueueModel]:
        """Start a queue (set state to 'started')"""
        with self._lock:
            with db.get_session() as session:
                queue = session.query(QueueModel).filter_by(id=queue_id).first()
                if not queue:
                    return None
                
                queue.state = 'started'
                session.commit()
                session.refresh(queue)
                
                message = f"Queue started: {queue.name}"
                output.info(message)
                self._log_to_queue_file(queue.name, message)
                return queue
    
    def stop_queue(self, queue_id: int) -> Optional[QueueModel]:
        """Stop a queue (set state to 'stopped')"""
        with self._lock:
            with db.get_session() as session:
                queue = session.query(QueueModel).filter_by(id=queue_id).first()
                if not queue:
                    return None
                
                queue.state = 'stopped'
                session.commit()
                session.refresh(queue)
                
                message = f"Queue stopped: {queue.name}"
                output.info(message)
                self._log_to_queue_file(queue.name, message)
                return queue
    
    def pause_queue(self, queue_id: int) -> Optional[QueueModel]:
        """Pause a queue (set state to 'paused')"""
        with self._lock:
            with db.get_session() as session:
                queue = session.query(QueueModel).filter_by(id=queue_id).first()
                if not queue:
                    return None
                
                queue.state = 'paused'
                session.commit()
                session.refresh(queue)
                
                message = f"Queue paused: {queue.name}"
                output.info(message)
                self._log_to_queue_file(queue.name, message)
                return queue
    
    def check_queue_state(self, queue_name: str) -> str:
        """Check if a queue can accept new jobs based on its state"""
        with db.get_session() as session:
            # Case-insensitive queue lookup
            queue = session.query(QueueModel).filter(
                QueueModel.name.ilike(queue_name)
            ).first()
            if not queue:
                raise ValueError(f"Queue '{queue_name}' not found")
            
            if queue.state == 'stopped':
                raise ValueError(f"Queue '{queue_name}' is stopped and cannot accept new jobs")
            
            if queue.state == 'paused':
                raise ValueError(f"Queue '{queue_name}' is paused and cannot accept new jobs")
            
            return queue.state
    
    def add_job(self, queue_name: str, job_id: int) -> bool:
        """Add a job to a queue (in-memory list)"""
        with self._lock:
            with db.get_session() as session:
                # Verify queue exists - case-insensitive lookup
                queue_model = session.query(QueueModel).filter(
                    QueueModel.name.ilike(queue_name)
                ).first()
                if not queue_model:
                    raise ValueError(f"Queue '{queue_name}' not found")
                
                # Use the actual queue name from the database
                actual_queue_name = queue_model.name
                
                # Block job submission if queue is not started
                if queue_model.state != 'started':
                    raise ValueError(f"Queue '{actual_queue_name}' is {queue_model.state} and cannot accept new jobs")
                
                # Verify job exists
                from models import Job as JobModel
                job = session.query(JobModel).filter_by(id=job_id).first()
                if not job:
                    raise ValueError(f"Job {job_id} not found")
                
                # Initialize queue list if it doesn't exist
                if actual_queue_name not in self._queues:
                    self._queues[actual_queue_name] = []
                
                # Add job to queue if not already there
                if job_id not in self._queues[actual_queue_name]:
                    self._queues[actual_queue_name].append(job_id)
                    message = f"Job {job_id} added"
                    output.info(message)
                    self._log_to_queue_file(actual_queue_name, message)
                else:
                    message = f"Job {job_id} already in queue {actual_queue_name}"
                    output.info(message)
                    self._log_to_queue_file(actual_queue_name, message)
                
                return True
    
    def get_queue_jobs(self, queue_name: str) -> List[int]:
        """Get list of job IDs in a queue"""
        with self._lock:
            return self._queues.get(queue_name, []).copy()
    
    def remove_job(self, queue_name: str, job_id: int) -> bool:
        """Remove a job from a queue"""
        with self._lock:
            if queue_name in self._queues and job_id in self._queues[queue_name]:
                self._queues[queue_name].remove(job_id)
                message = f"Job {job_id} removed from queue {queue_name}"
                output.info(message)
                self._log_to_queue_file(queue_name, message)
                return True
            return False
    
    def get_next_job(self, queue_name: str) -> Optional[int]:
        """Get the next job from a queue (FIFO)"""
        with self._lock:
            if queue_name in self._queues and self._queues[queue_name]:
                job_id = self._queues[queue_name].pop(0)
                # Don't log popped messages - too verbose
                return job_id
            return None
    
    def get_queue_size(self, queue_name: str) -> int:
        """Get the number of jobs in a queue"""
        with self._lock:
            return len(self._queues.get(queue_name, []))
    
    def get_all_queue_jobs(self) -> Dict[str, List[int]]:
        """Get all jobs from all queues"""
        all_jobs = {}
        try:
            with self._lock:
                # Return a copy of the current queue state
                for queue_name, job_ids in self._queues.items():
                    if job_ids:  # Only include queues that have jobs
                        all_jobs[queue_name] = job_ids.copy()
            
            return all_jobs
        except Exception as e:
            output.error(f"Error getting all queue jobs: {e}")
            return {}
    
    def clear_queue(self, queue_name: str) -> int:
        """Clear all jobs from a queue, return count of cleared jobs"""
        with self._lock:
            if queue_name in self._queues:
                count = len(self._queues[queue_name])
                self._queues[queue_name].clear()
                output.info(f"Cleared {count} jobs from queue {queue_name}")
                return count
            return 0

    def _start_dispatcher(self):
        """Start the queue dispatcher background thread"""
        if not self._dispatcher_running:
            self._dispatcher_running = True
            self._dispatcher_thread = Thread(target=self._dispatcher_loop, daemon=True)
            self._dispatcher_thread.start()
            output.info("Queue dispatcher thread started")

    def _should_retry_dispatch_failure(self, reason: str) -> bool:
        """Determine if a dispatch failure should be retried or is permanent"""
        # Temporary failures that should be retried
        temporary_failures = [
            "No workers assigned",
            "No started and online workers available", 
            "No workers with available capacity"
        ]
        
        # Permanent failures that should fail the job
        permanent_failures = [
            "rejected job",
            "Exception during dispatch",
            "Server error",
            "Internal Server Error",
            "Failed to start command",
            "Connection refused",
            "timeout"
        ]
        
        # Check for temporary failures first
        for temp_failure in temporary_failures:
            if temp_failure in reason:
                return True
                
        # Check for permanent failures
        for perm_failure in permanent_failures:
            if perm_failure.lower() in reason.lower():
                return False
                
        # Default to retry for unknown errors to avoid losing jobs
        return True
    
    def _log_dispatch_failure_to_job(self, job_id: int, message: str):
        """Log dispatch failure message to individual job log file"""
        try:
            from job import job as job_module
            job_module.append_to_log(job_id, f"[DISPATCH] {message}")
        except Exception as e:
            output.error(f"Failed to log dispatch failure to job {job_id}: {e}")

    def _dispatcher_loop(self):
        """Main dispatcher loop - runs in background thread"""
        output.info("Queue dispatcher started")
        
        while self._dispatcher_running:
            try:
                # Process all started queues
                with db.get_session() as session:
                    # Get all started queues ordered by priority
                    started_queues = session.query(QueueModel)\
                        .filter_by(state='started')\
                        .order_by(QueueModel.priority)\
                        .all()
                    
                    output.debug(f"Found {len(started_queues)} started queues")
                    for queue_model in started_queues:
                        if not self._dispatcher_running:
                            break
                        
                        # Keep dispatching jobs from this queue until no more capacity or no more jobs
                        while self._dispatcher_running:
                            job_id = self.get_next_job(queue_model.name)
                            if job_id is None:
                                break  # No more jobs in queue
                            
                            # Try to dispatch the job
                            success, reason = self._dispatch_job(queue_model, job_id)
                            if success:
                                # reason always contains worker info now
                                message = f"Dispatched job {job_id} to {reason}"
                                output.info(message)
                                self._log_to_queue_file(queue_model.name, message)
                            else:
                                # Handle different types of dispatch failures
                                should_retry = self._should_retry_dispatch_failure(reason)
                                
                                if should_retry:
                                    # Temporary failures - put job back in queue for retry
                                    with self._lock:
                                        if queue_model.name not in self._queues:
                                            self._queues[queue_model.name] = []
                                        self._queues[queue_model.name].append(job_id)
                                    message = f"Failed to dispatch job {job_id} ({reason}) - will retry"
                                    output.warning(message)
                                    self._log_to_queue_file(queue_model.name, message)
                                    # Also log to job file for user visibility
                                    self._log_dispatch_failure_to_job(job_id, f"Dispatch failed: {reason} - retrying...")
                                else:
                                    # Permanent failures - mark job as failed
                                    error_message = f"Job dispatch failed permanently: {reason}"
                                    from job import job as job_module
                                    job_module.update_error(job_id, error_message)
                                    
                                    message = f"Job {job_id} marked as failed due to permanent dispatch error: {reason}"
                                    output.error(message)
                                    self._log_to_queue_file(queue_model.name, message)
                                
                                break  # Break out of dispatch loop for this queue
                
                # Sleep between polling cycles
                if self._dispatcher_running:
                    time.sleep(5.0)  # Poll every 5 seconds
                    
            except Exception as e:
                output.error(f"Error in queue dispatcher: {e}")
                time.sleep(5.0)  # Wait longer on error
        
        output.info("Queue dispatcher stopped")

    def _get_worker_running_jobs_count(self, worker_name: str) -> int:
        """Get count of running jobs for a specific worker"""
        try:
            from models import Job as JobModel
            from states import states
            
            with db.get_session() as session:
                running_count = session.query(JobModel).filter(
                    JobModel.assigned_worker_name == worker_name,
                    JobModel.status.in_([states.RUNNING, 'RUNNING', 'Running', 'DISPATCHED'])
                ).count()
                
                return running_count
        except Exception as e:
            output.error(f"Error counting running jobs for worker {worker_name}: {e}")
            return 0

    def _dispatch_job(self, queue_model: QueueModel, job_id: int) -> Tuple[bool, str]:
        """Dispatch a single job to a worker, returns (success, reason)"""
        try:
            # Get available workers for this queue
            workers = self.get_queue_workers_by_name(queue_model.name)
            
            if not workers:
                return False, "No workers assigned"
            
            # Filter for workers that are both started AND online (exclude paused workers)
            available_workers_by_state = [w for w in workers if w.state == 'started' and w.status == 'online']
            output.debug(f"After filtering for 'started' state and 'online' status: {len(available_workers_by_state)} workers")
            for i, w in enumerate(available_workers_by_state):
                output.debug(f"Available worker {i}: id={w.id}, name={w.name}, state={w.state}, status={w.status}")
            
            if not available_workers_by_state:
                return False, "No started and online workers available"
            
            # Filter for workers with available capacity
            available_workers = []
            for worker in available_workers_by_state:
                running_jobs = self._get_worker_running_jobs_count(worker.name)
                output.debug(f"Worker {worker.name}: {running_jobs}/{worker.max_jobs} jobs running")
                if running_jobs < worker.max_jobs:
                    available_workers.append(worker)
            
            if not available_workers:
                return False, "No workers with available capacity"
            
            # For now, use simple round-robin selection
            # TODO: Implement proper strategy selection
            selected_worker = available_workers[0]  # Simple selection for MVP
            
            # Create execution_id in format queue_name:job_id
            execution_id = f"{queue_model.name}:{job_id}"
            
            # Get job details
            with db.get_session() as session:
                from models import Job as JobModel, JobSpec as SpecModel
                job = session.query(JobModel).filter_by(id=job_id).first()
                if not job:
                    return False, "Job not found in database"
                
                # Get job spec to build command
                spec = session.query(SpecModel).filter_by(name=job.name).first()
                if not spec:
                    # Mark job as failed - spec not found is a permanent error
                    error_message = f"Spec '{job.name}' not found"
                    
                    # Use the job module's update_error method to properly handle the failure
                    # This will set status to Failed, update error_message, and log to job file
                    from job import job as job_module
                    job_module.update_error(job_id, error_message)
                    
                    return True, f"worker {selected_worker.name}"  # Don't retry - this is a permanent error
                
                # Build command with template substitution
                command = spec.command
                args = []
                job_args = {}

                # Extract runtime_args from job parameters
                if job.parameters:
                    try:
                        params = json.loads(job.parameters) if isinstance(job.parameters, str) else job.parameters
                        if isinstance(params, dict) and 'runtime_args' in params:
                            job_args = params['runtime_args']
                        else:
                            job_args = params
                    except (json.JSONDecodeError, TypeError):
                        output.warning(f"Failed to parse job parameters for job {job_id}: {job.parameters}")

                # Check if command uses template substitution ({{key}} syntax)
                import re
                template_pattern = re.compile(r'\{\{(\w+)\}\}')
                if template_pattern.search(command):
                    # Substitute {{key}} with values from job_args
                    def replace_template(match):
                        key = match.group(1)
                        if isinstance(job_args, dict) and key in job_args:
                            return str(job_args[key])
                        else:
                            output.warning(f"Template key '{key}' not found in job args for job {job_id}")
                            return match.group(0)  # Leave placeholder as-is

                    command = template_pattern.sub(replace_template, command)
                    output.debug(f"Substituted command for job {job_id}: {command}")
                elif job_args:
                    # No template - pass args as JSON for backwards compatibility
                    args.append(json.dumps(job_args))
                
                # Dispatch to worker using async/await in thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Import worker here to avoid circular imports
                    from worker import worker
                    
                    success = loop.run_until_complete(
                        worker.execute_command(selected_worker.id, execution_id, command, args)
                    )
                    
                    if success:
                        # Update job with assigned worker name in database
                        job.assigned_worker_name = selected_worker.name
                        job.worker_name = selected_worker.name  # Also set worker_name for UI display
                        session.commit()
                        
                        return True, f"worker {selected_worker.name}"
                    else:
                        # Get more detailed error information if available
                        detailed_reason = f"Worker {selected_worker.name} rejected job (communication successful but execution failed)"
                        return False, detailed_reason
                        
                finally:
                    loop.close()
                    
        except Exception as e:
            return False, f"Exception during dispatch: {str(e)}"

    def get_log_file_path(self, queue_id: int) -> Optional[str]:
        """Get the log file path for a queue from database"""
        try:
            queue_record = self.get_by_id(queue_id)
            if not queue_record:
                return None
            return queue_record.log_file_path
        except Exception as e:
            output.error(f"Error getting log file path for queue {queue_id}: {e}")
            return None

    def get_log_content(self, queue_id: int) -> Optional[str]:
        """Get the log content for a queue"""
        try:
            log_file_path = self.get_log_file_path(queue_id)
            if not log_file_path:
                return f"No log file path configured for queue {queue_id}"
                
            # Create the log file if it doesn't exist, then read it
            if not os.path.exists(log_file_path):
                # Create empty log file
                os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
                with open(log_file_path, 'w', encoding='utf-8') as f:
                    f.write("")
                    
            with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
                # Always return something - empty string breaks frontend LogViewer
                return content if content.strip() else "(no logs yet)"
        except Exception as e:
            output.error(f"Error reading log file for queue {queue_id}: {e}")
            return f"Error reading log file for queue {queue_id}: {str(e)}"

    def clear_log_content(self, queue_id: int) -> bool:
        """Clear the log content for a queue (truncate the log file)"""
        try:
            log_file_path = self.get_log_file_path(queue_id)
            if not log_file_path:
                output.error(f"No log file path found for queue {queue_id}")
                return False
                
            # Create the log file if it doesn't exist, or truncate it if it does
            with open(log_file_path, 'w', encoding='utf-8') as f:
                f.write("")  # Truncate the file
            
            output.info(f"Cleared log file for queue {queue_id}")
            return True
        except Exception as e:
            output.error(f"Error clearing log file for queue {queue_id}: {e}")
            return False

# Create singleton instance
queue = Queue()
