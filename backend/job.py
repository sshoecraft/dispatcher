from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from contextlib import contextmanager
import json
import os
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from info import info
from output import output
from db import db
from models import Job as JobModel
from states import states
import pytz

class Job:
    def __init__(self):
        self._lock = Lock()
        self._initialized = False
    
    def initialize(self):
        """Initialize job - called at startup"""
        with self._lock:
            if not self._initialized:
                try:
                    # Ensure logs directory exists
                    self._ensure_log_directory()
                    self._initialized = True
                    output.info("Job initialized successfully")
                except Exception as e:
                    output.error(f"Failed to initialize job: {e}")
                    raise
    
    def _ensure_log_directory(self):
        """Ensure the logs directory exists"""
        log_dir = Path(info.prefix) / 'logs' / 'jobs'
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    
    def create(
        self,
        name: str,
        args: Optional[Dict] = None,
        created_by: str = "system",
        target_queue: Optional[str] = None
    ) -> JobModel:
        """Create a new job record in the database"""
        with self._lock:
            with db.get_session() as session:
                # Create structured parameters with all job metadata
                parameters = {
                    "spec_name": name,
                    "created_by": created_by,
                    "runtime_args": args or {}
                }
                
                # Create basic job record
                job = JobModel(
                    name=name,
                    status=states.PENDING,
                    created_by=created_by,
                    parameters=parameters,
                    queue_name=target_queue,  # Set initial queue assignment
                    log_file_path=None  # Will be set after we get the job ID
                )
                
                session.add(job)
                session.commit()
                session.refresh(job)
                
                # Create log file with job ID
                log_dir = self._ensure_log_directory()
                log_file_path = log_dir / f"{job.id}.log"
                
                # Initialize detailed log file header
                with open(log_file_path, 'w') as f:
                    f.write(f"=== Job {job.id} Log ===\n")
                    f.write(f"Job Name: {name}\n")
                    f.write(f"Created By: {created_by}\n")
                    f.write(f"Created At: {datetime.now().isoformat()}\n")
                    if args:
                        f.write(f"Parameters: {args}\n")
                    f.write(f"Queue: {target_queue}\n")
                    f.write("Job created and awaiting queue assignment...\n\n")
                    f.write("=" * 50 + "\n\n")
                
                # Update job with log file path
                job.log_file_path = str(log_file_path)
                session.commit()
                
                output.info(f"Created job {job.id} for user {created_by}")
                return job
    
    def get_by_id(self, db_session: Session, job_id: int) -> Optional[JobModel]:
        """Get job by database ID"""
        return db_session.query(JobModel).filter(JobModel.id == job_id).first()
    
    def list(
        self,
        db_session: Session,
        limit: int = 100,
        offset: int = 0,
        status_filter: Optional[str] = None,
        user_filter: Optional[str] = None
    ) -> List[JobModel]:
        """Get all jobs with filtering"""
        query = db_session.query(JobModel)
        
        if status_filter:
            query = query.filter(JobModel.status == status_filter)
        
        
        if user_filter:
            query = query.filter(JobModel.created_by == user_filter)
        
        return query.order_by(desc(JobModel.created_at)).offset(offset).limit(limit).all()
    
    def list_with_count(
        self,
        limit: int = 100,
        offset: int = 0,
        status_filter: Optional[str] = None,
        exclude_statuses: Optional[List[str]] = None,
        user_filter: Optional[str] = None,
        name_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: str = 'UTC',
        runtime_args_filter: Optional[str] = None
    ) -> tuple[List[JobModel], int]:
        """Get all jobs with filtering and total count for pagination

        Date parameters (start_date, end_date) are ISO format strings interpreted in the specified timezone.
        Dates are converted to UTC for database queries.
        Timezone defaults to server local time (UTC).

        runtime_args_filter format: 'key1:value1,key2:value2' for filtering on runtime_args JSON fields.
        Example: 'asset_control_id:24,technology_type:Windows'
        """
        with db.get_session() as session:
            query = session.query(JobModel)

            if status_filter:
                query = query.filter(JobModel.status == status_filter)

            if exclude_statuses:
                query = query.filter(~JobModel.status.in_(exclude_statuses))


            if user_filter:
                query = query.filter(JobModel.created_by == user_filter)

            if name_filter:
                query = query.filter(JobModel.name.ilike(f'%{name_filter}%'))

            # Runtime args filtering - query JSON fields
            if runtime_args_filter:
                try:
                    from sqlalchemy import text
                    filters = runtime_args_filter.split(',')
                    for idx, filter_item in enumerate(filters):
                        if ':' in filter_item:
                            key, value = filter_item.split(':', 1)
                            key = key.strip()
                            value = value.strip()
                            # Query the nested JSON field using text SQL fragment
                            # parameters->'runtime_args'->>'key' = value
                            # Use unique bind param name for each filter to avoid conflicts
                            param_name = f"value_{idx}"
                            query = query.filter(
                                text(f"parameters->'runtime_args'->>'{key}' = :{param_name}").bindparams(**{param_name: value})
                            )
                            output.info(f"Runtime args filter: {key}={value}")
                        else:
                            output.error(f"Invalid runtime_args_filter format: {filter_item}. Expected 'key:value'")
                except Exception as e:
                    output.error(f"Error parsing runtime_args_filter: {e}")

            # Date range filtering
            if start_date or end_date:
                try:
                    tz = pytz.timezone(timezone)

                    # Parse and convert start date
                    if start_date:
                        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                        if start_dt.tzinfo is None:
                            start_dt = tz.localize(start_dt)
                        start_dt_utc = start_dt.astimezone(pytz.UTC).replace(tzinfo=None)
                        query = query.filter(JobModel.created_at >= start_dt_utc)
                        output.info(f"Date filter: start={start_date} ({timezone}) -> {start_dt_utc} (UTC)")

                    # Parse and convert end date
                    if end_date:
                        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                        if end_dt.tzinfo is None:
                            end_dt = tz.localize(end_dt)
                        end_dt_utc = end_dt.astimezone(pytz.UTC).replace(tzinfo=None)
                        query = query.filter(JobModel.created_at <= end_dt_utc)
                        output.info(f"Date filter: end={end_date} ({timezone}) -> {end_dt_utc} (UTC)")
                except Exception as e:
                    output.error(f"Error parsing date filters: {e}")

            # Get total count
            total = query.count()

            # Get paginated results
            jobs = query.order_by(desc(JobModel.created_at)).offset(offset).limit(limit).all()

            return jobs, total
    
    def list_by_user(
        self,
        db_session: Session,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        status_filter: Optional[str] = None,
    ) -> List[JobModel]:
        """Get jobs for a specific user with filtering"""
        query = db_session.query(JobModel).filter(JobModel.created_by == user_id)
        
        if status_filter:
            query = query.filter(JobModel.status == status_filter)
        
        
        return query.order_by(desc(JobModel.created_at)).offset(offset).limit(limit).all()
    
    def update_status(
        self,
        db_session: Session,
        job_id: int,
        status: str,
        progress: Optional[int] = None,
        result: Optional[Dict] = None,
        error_message: Optional[str] = None,
        worker_name: Optional[str] = None
    ) -> Optional[JobModel]:
        """Update job status and related fields"""
        job = db_session.query(JobModel).filter(JobModel.id == job_id).first()
        if not job:
            return None
        
        job.status = status
        
        if progress is not None:
            job.progress = progress
        
        if result is not None:
            job.result = result
        
        if error_message is not None:
            job.error_message = error_message
        
        if worker_name is not None:
            job.worker_name = worker_name
        
        # Update timestamps based on status
        now = datetime.utcnow()
        if status == states.RUNNING and not job.started_at:
            job.started_at = now
        elif states.is_terminal(status) and not job.completed_at:
            job.completed_at = now
        
        db_session.commit()
        db_session.refresh(job)
        
        output.info(f"Updated job {job_id} status to {status}")
        return job
    
    def cancel(self, db_session: Session, job_id: int) -> bool:
        """Cancel a job - Queue will handle worker communication"""
        try:
            job = db_session.query(JobModel).filter(JobModel.id == job_id).first()
            if job:
                job.status = states.CANCELLED
                job.completed_at = datetime.now()
                db_session.commit()
                output.info(f"Cancelled job {job_id}")
                return True
            return False
            
        except Exception as e:
            output.error(f"Error cancelling job {job_id}: {e}")
            return False
    
    def retry(
        self,
        db_session: Session,
        job_id: int,
        user_id: str
    ) -> Optional[int]:
        """Retry a failed job by creating a new job record"""
        job = db_session.query(JobModel).filter(JobModel.id == job_id).first()
        
        # Check if job exists and is in a retryable state
        if not job:
            output.warning(f"Job not found for retry: {job_id}")
            return None
            
        if not states.is_retryable(job.status):
            output.warning(f"Job {job_id} cannot be retried - status: '{job.status}'")
            return None
        
        try:
            # Create new job record (Queue will handle execution)
            new_job = self.create(
                name=job.name,
                args=job.parameters,
                created_by=user_id
            )
            
            # Update retry count on original job
            job.retries += 1
            db_session.commit()
            
            output.info(f"Retried job {job_id} as new job {new_job.id}")
            return new_job.id
            
        except Exception as e:
            output.error(f"Error retrying job {job_id}: {e}")
            return None
    
    def get_statistics(self, db_session: Session, days: int = 7) -> Dict[str, Any]:
        """Get job statistics - total system stats (not filtered by date)"""

        # Basic counts - ALL jobs, not filtered by date
        total = db_session.query(JobModel).count()

        # Count completed/success jobs (handle both old SUCCESS and new Completed)
        success = db_session.query(JobModel).filter(
            JobModel.status.in_([states.COMPLETED, 'SUCCESS', 'Completed'])
        ).count()

        # Count failed/failure jobs (handle both old FAILURE and new Failed)
        failure = db_session.query(JobModel).filter(
            JobModel.status.in_([states.FAILED, 'FAILURE', 'Failed'])
        ).count()

        # Count running jobs (handle variations)
        running = db_session.query(JobModel).filter(
            JobModel.status.in_([states.RUNNING, 'RUNNING', 'Running', 'DISPATCHED'])
        ).count()

        # Count pending jobs (handle case variations)
        pending = db_session.query(JobModel).filter(
            JobModel.status.in_([states.PENDING, 'PENDING', 'Pending'])
        ).count()


        # Average duration for ALL completed jobs
        completed_jobs = db_session.query(JobModel).filter(
            JobModel.started_at.isnot(None),
            JobModel.completed_at.isnot(None)
        ).all()

        durations = [
            (job.completed_at - job.started_at).total_seconds()
            for job in completed_jobs
        ]

        avg_duration = sum(durations) / len(durations) if durations else 0

        # Get jobs from last 24 hours
        last_24h_cutoff = datetime.utcnow() - timedelta(hours=24)
        jobs_last_24h = db_session.query(JobModel).filter(
            JobModel.created_at >= last_24h_cutoff
        ).all()

        jobs_last_24h_count = len(jobs_last_24h)

        # Calculate job spec distribution for ALL jobs
        from collections import Counter
        spec_distribution = Counter()

        # Get spec names from ALL jobs
        all_jobs = db_session.query(JobModel).all()

        for job_record in all_jobs:
            if job_record.parameters and isinstance(job_record.parameters, dict):
                spec_name = job_record.parameters.get('spec_name', 'Unknown')
                spec_distribution[spec_name] += 1

        # Convert to list of dicts for frontend
        spec_distribution_list = [
            {'name': spec, 'value': count}
            for spec, count in spec_distribution.most_common()
        ]

        # Calculate total runtime for last 24h jobs
        durations_24h = []
        for job_record in jobs_last_24h:
            if job_record.started_at and job_record.completed_at:
                duration = (job_record.completed_at - job_record.started_at).total_seconds()
                durations_24h.append(duration)

        total_runtime_24h_seconds = sum(durations_24h)
        avg_duration_24h = sum(durations_24h) / len(durations_24h) if durations_24h else 0

        # Calculate total runtime (sum of all job durations)
        total_runtime_seconds = sum(durations)
        
        return {
            "period_days": days,
            "total_jobs": total,
            "completed_jobs": success,  # Frontend expects this name
            "failed_jobs": failure,      # Frontend expects this name
            "running_jobs": running,     # Frontend expects this name
            "pending_jobs": pending,     # Frontend expects this name
            "jobs_last_24h": jobs_last_24h_count,
            "avg_job_duration_minutes": (avg_duration / 60) if avg_duration else 0,
            "total_runtime_minutes": (total_runtime_seconds / 60) if total_runtime_seconds else 0,
            "success_rate": (success / total * 100) if total > 0 else 0,
            "failure_rate": (failure / total * 100) if total > 0 else 0,
            "average_duration_seconds": avg_duration,
            "spec_distribution": spec_distribution_list,
            "total_runtime_24h_minutes": (total_runtime_24h_seconds / 60) if total_runtime_24h_seconds else 0,
            "avg_job_duration_24h_minutes": (avg_duration_24h / 60) if avg_duration_24h else 0,
        }
    
    def delete(self, db_session: Session, job_id: int) -> bool:
        """Delete a specific job entry by database ID"""
        try:
            job = db_session.query(JobModel).filter(JobModel.id == job_id).first()
            if not job:
                return False
            
            # Delete log file if exists
            if job.log_file_path and os.path.exists(job.log_file_path):
                try:
                    os.remove(job.log_file_path)
                    output.info(f"Deleted log file: {job.log_file_path}")
                except Exception as e:
                    output.error(f"Failed to delete log file {job.log_file_path}: {e}")
            
            db_session.delete(job)
            db_session.commit()
            
            output.info(f"Deleted job {job_id}")
            return True
            
        except Exception as e:
            output.error(f"Error deleting job {job_id}: {e}")
            return False
    
    def cleanup_by_status(
        self,
        db_session: Session,
        statuses: List[str],
        days_old: int = 30
    ) -> int:
        """Clean up jobs with specific statuses older than specified days"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        old_jobs = db_session.query(JobModel).filter(
            JobModel.created_at < cutoff_date,
            JobModel.status.in_(statuses)
        )
        
        # Delete log files
        for job in old_jobs:
            if job.log_file_path and os.path.exists(job.log_file_path):
                try:
                    os.remove(job.log_file_path)
                except Exception as e:
                    output.error(f"Failed to delete log file {job.log_file_path}: {e}")
        
        count = old_jobs.count()
        old_jobs.delete()
        db_session.commit()
        
        output.info(f"Cleaned up {count} jobs with statuses {statuses} older than {days_old} days")
        return count
    
    def cleanup_old(self, db_session: Session, days_old: int = 30) -> int:
        """Clean up completed jobs older than specified days"""
        return self.cleanup_by_status(
            db_session,
            states.get_terminal_states(),
            days_old
        )
    
    
    
    
    def append_to_log(self, job_id: int, log_content: str) -> bool:
        """Append content to a job's log file"""
        try:
            log_dir = self._ensure_log_directory()
            log_file_path = log_dir / f"{job_id}.log"
            
            with open(log_file_path, 'a') as f:
                f.write(log_content)
                if not log_content.endswith('\n'):
                    f.write('\n')
            
            return True
        except Exception as e:
            output.error(f"Failed to append to log for job {job_id}: {e}")
            return False
    
    def get_log_content(self, job_id: int) -> Optional[str]:
        """Get the content of a job's log file"""
        try:
            # Get the log file path from the database
            with db.get_session() as session:
                job_record = session.query(JobModel).filter(JobModel.id == job_id).first()
                if not job_record:
                    return f"Error: Job {job_id} not found in database"
                
                if not job_record.log_file_path:
                    return f"Error: No log file path configured for job {job_id}"
                
                log_file_path = Path(job_record.log_file_path)
                
                # Create the log file if it doesn't exist, then read it
                if not log_file_path.exists():
                    log_file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(log_file_path, 'w', encoding='utf-8') as f:
                        f.write("")
                
                with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    # Always return something - empty string breaks frontend LogViewer
                    return content if content.strip() else "(no logs yet)"
            
            return None
        except Exception as e:
            output.error(f"Failed to read log for job {job_id}: {e}")
            return None
    
    def update_progress(self, job_id: int, progress: int):
        """Update job progress percentage"""
        try:
            with db.get_session() as db_session:
                job_record = db_session.query(JobModel).filter(JobModel.id == job_id).first()
                if job_record:
                    # Set status to Running if it's still Pending
                    status = job_record.status
                    if status == 'Pending':
                        status = 'Running'
                    self.update_status(db_session, job_id, status, progress=progress)
                    db_session.commit()
                    output.info(f"Updated progress for job {job_id} to {progress}%")
        except Exception as e:
            output.error(f"Failed to update progress for job {job_id}: {e}")
    
    def update_result(self, job_id: int, result: dict):
        """Update job result"""
        try:
            with db.get_session() as db_session:
                job_record = db_session.query(JobModel).filter(JobModel.id == job_id).first()
                if job_record:
                    # Don't change status if job is already completed/failed
                    status = job_record.status
                    if status not in ['Completed', 'Failed']:
                        status = 'Completed'
                    self.update_status(db_session, job_id, status, result=result)
                    db_session.commit()
                    output.info(f"Updated result for job {job_id}")
        except Exception as e:
            output.error(f"Failed to update result for job {job_id}: {e}")
    
    def update_error(self, job_id: int, error_message: str):
        """Update job error message and set status to Failed"""
        try:
            with db.get_session() as db_session:
                job_record = db_session.query(JobModel).filter(JobModel.id == job_id).first()
                if job_record:
                    # Always set status to Failed when ERROR= is found
                    # Only update error message if it's not already set (preserve application errors)
                    if not job_record.error_message or job_record.error_message.strip() == "":
                        job_record.error_message = error_message
                    else:
                        output.debug(f"Error message for job {job_id} already set, preserving existing: {job_record.error_message}")
                    
                    job_record.status = 'Failed'
                    db_session.commit()
                    output.info(f"Updated job {job_id} to Failed with error: {error_message}")
                    
                    # Also append error message to log file
                    self.append_to_log(job_id, f"Job failed with error: {error_message}")
        except Exception as e:
            output.error(f"Failed to update error for job {job_id}: {e}")
    

# Create singleton instance
job = Job()
