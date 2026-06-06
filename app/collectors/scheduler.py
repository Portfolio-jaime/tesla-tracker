"""
CollectorScheduler - Manages automated execution of data collectors using APScheduler.

This module provides a scheduler that automatically runs ReservationCollector and
ShippingCollector at configured intervals.
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.job import Job
from pytz import utc

from app.collectors.reservation import ReservationCollector
from app.collectors.shipping import ShippingCollector

logger = logging.getLogger(__name__)


class CollectorScheduler:
    """
    Manages scheduled execution of data collectors.
    
    Handles scheduling and execution of ReservationCollector and ShippingCollector
    with configurable intervals and comprehensive logging.
    """
    
    # Configuration for job scheduling
    JOB_CONFIG = {
        "reservation": {
            "interval_hours": 6,
            "collector_class": ReservationCollector,
            "job_id": "reservation_collector",
        },
        "shipping": {
            "interval_hours": 3,
            "collector_class": ShippingCollector,
            "job_id": "shipping_collector",
        },
    }
    
    def __init__(self):
        """Initialize the CollectorScheduler."""
        self.scheduler: Optional[BackgroundScheduler] = None
        self.jobs: Dict[str, Job] = {}
        self.logger = logging.getLogger(__name__)
        self._running = False
    
    def start_scheduler(self) -> None:
        """
        Start the background scheduler.
        
        Raises:
            RuntimeError: If scheduler is already running.
        """
        if self._running:
            self.logger.warning("Scheduler is already running")
            raise RuntimeError("Scheduler is already running")
        
        try:
            self.logger.info("Starting CollectorScheduler...")
            
            self.scheduler = BackgroundScheduler(timezone=utc)
            self.add_job_collectors()
            self.scheduler.start()
            
            self._running = True
            self.logger.info("CollectorScheduler started successfully")
            
        except Exception as e:
            self.logger.error(f"Error starting scheduler: {str(e)}", exc_info=True)
            self._running = False
            raise
    
    def stop_scheduler(self) -> None:
        """
        Stop the background scheduler.
        
        Raises:
            RuntimeError: If scheduler is not running.
        """
        if not self._running or not self.scheduler:
            self.logger.warning("Scheduler is not running")
            raise RuntimeError("Scheduler is not running")
        
        try:
            self.logger.info("Stopping CollectorScheduler...")
            self.scheduler.shutdown(wait=True)
            self._running = False
            self.scheduler = None
            self.jobs.clear()
            self.logger.info("CollectorScheduler stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error stopping scheduler: {str(e)}", exc_info=True)
            raise
    
    def add_job_collectors(self) -> None:
        """
        Add scheduled jobs for all collectors.
        
        Creates jobs for:
        - ReservationCollector: Every 6 hours
        - ShippingCollector: Every 3 hours
        
        Raises:
            RuntimeError: If scheduler is not initialized.
        """
        if not self.scheduler:
            raise RuntimeError("Scheduler not initialized. Call start_scheduler first.")
        
        try:
            self.logger.info("Adding collector jobs to scheduler...")
            
            for collector_name, config in self.JOB_CONFIG.items():
                try:
                    job_id = config["job_id"]
                    interval_hours = config["interval_hours"]
                    collector_class = config["collector_class"]
                    
                    self.logger.info(
                        f"Adding job for {collector_name} collector "
                        f"(interval: {interval_hours} hours, job_id: {job_id})"
                    )
                    
                    job = self.scheduler.add_job(
                        self._run_collector_wrapper,
                        IntervalTrigger(hours=interval_hours, timezone=utc),
                        id=job_id,
                        name=f"{collector_name} Collector",
                        args=(collector_class, collector_name),
                        max_instances=1,
                        replace_existing=True,
                    )
                    
                    self.jobs[job_id] = job
                    self.logger.info(f"Successfully added job: {job_id}")
                    
                except Exception as e:
                    self.logger.error(
                        f"Error adding job for {collector_name}: {str(e)}",
                        exc_info=True,
                    )
                    raise
            
            self.logger.info(f"Successfully added {len(self.jobs)} collector jobs")
            
        except Exception as e:
            self.logger.error(f"Error adding collector jobs: {str(e)}", exc_info=True)
            raise
    
    def _run_collector_wrapper(
        self, collector_class: type, collector_name: str
    ) -> Dict[str, Any]:
        """
        Wrapper function to execute a collector with proper logging and error handling.
        
        Args:
            collector_class: The collector class to instantiate and run
            collector_name: Name of the collector for logging purposes
            
        Returns:
            Dictionary with execution results
        """
        start_time = datetime.utcnow()
        result = {
            "collector": collector_name,
            "start_time": start_time,
            "end_time": None,
            "duration_seconds": None,
            "success": False,
            "error": None,
            "result": None,
        }
        
        try:
            self.logger.info(f"[{collector_name}] Collector job started")
            
            # Instantiate collector
            collector = collector_class()
            
            # Run collector
            result["result"] = collector.run()
            result["success"] = True
            
            self.logger.info(
                f"[{collector_name}] Collector job completed successfully. "
                f"Result: {result['result']}"
            )
            
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            self.logger.error(
                f"[{collector_name}] Collector job failed with error: {str(e)}",
                exc_info=True,
            )
        
        finally:
            result["end_time"] = datetime.utcnow()
            if result["start_time"] and result["end_time"]:
                duration = result["end_time"] - result["start_time"]
                result["duration_seconds"] = duration.total_seconds()
            
            self.logger.info(
                f"[{collector_name}] Collector job finished. "
                f"Duration: {result['duration_seconds']:.2f}s, "
                f"Success: {result['success']}"
            )
        
        return result
    
    def get_job_status(self) -> Dict[str, Any]:
        """
        Get the status of all scheduled jobs.
        
        Returns:
            Dictionary containing:
                - scheduler_running: Whether scheduler is running
                - jobs_count: Number of scheduled jobs
                - jobs: Dict of job details (id, name, next_run_time, trigger)
                - timestamp: Current UTC timestamp
        """
        jobs_info = {}
        
        if self.scheduler and self._running:
            for job in self.scheduler.get_jobs():
                jobs_info[job.id] = {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time,
                    "trigger": str(job.trigger),
                    "func_name": job.func_ref,
                    "max_instances": job.max_instances,
                }
        
        return {
            "scheduler_running": self._running,
            "jobs_count": len(jobs_info),
            "jobs": jobs_info,
            "timestamp": datetime.utcnow(),
        }
    
    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running


# Global scheduler instance
_scheduler_instance: Optional[CollectorScheduler] = None


def get_scheduler() -> CollectorScheduler:
    """
    Get or create the global scheduler instance.
    
    Returns:
        CollectorScheduler: The global scheduler instance
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = CollectorScheduler()
    return _scheduler_instance


def initialize_scheduler() -> CollectorScheduler:
    """
    Initialize and start the global scheduler.
    
    Returns:
        CollectorScheduler: The started scheduler instance
        
    Raises:
        RuntimeError: If scheduler fails to start
    """
    scheduler = get_scheduler()
    if not scheduler.is_running:
        scheduler.start_scheduler()
    return scheduler


def shutdown_scheduler() -> None:
    """Shutdown the global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance and _scheduler_instance.is_running:
        _scheduler_instance.stop_scheduler()
        _scheduler_instance = None
