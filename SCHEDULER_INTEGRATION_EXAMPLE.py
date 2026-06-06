"""
Example: Integration of CollectorScheduler with FastAPI

This file shows how to integrate the CollectorScheduler with a FastAPI application.
You can add this code to your main FastAPI application (app/api/main.py).
"""

from fastapi import FastAPI
from datetime import datetime
from app.collectors.scheduler import initialize_scheduler, shutdown_scheduler, get_scheduler

# Example FastAPI application setup
app = FastAPI(
    title="Tesla Tracker",
    version="1.0.0",
    description="API for tracking Tesla vehicle reservations and deliveries"
)


# ============================================================================
# SCHEDULER LIFECYCLE EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """
    Initialize scheduler on application startup.
    
    This event is triggered when the FastAPI application starts.
    The scheduler will run in the background, executing collectors
    at their configured intervals.
    """
    print("Starting up... Initializing CollectorScheduler")
    try:
        initialize_scheduler()
        print("CollectorScheduler initialized and started successfully")
    except Exception as e:
        print(f"Error starting scheduler: {e}")
        # Optionally re-raise the exception to fail startup
        # raise


@app.on_event("shutdown")
async def shutdown_event():
    """
    Shutdown scheduler on application shutdown.
    
    This event is triggered when the FastAPI application shuts down.
    The scheduler will be gracefully stopped and all resources cleaned up.
    """
    print("Shutting down... Stopping CollectorScheduler")
    try:
        shutdown_scheduler()
        print("CollectorScheduler stopped successfully")
    except Exception as e:
        print(f"Error stopping scheduler: {e}")


# ============================================================================
# SCHEDULER STATUS ENDPOINTS
# ============================================================================

@app.get("/api/v1/scheduler/status", tags=["Scheduler"])
async def get_scheduler_status():
    """
    Get the current status of the scheduler and its jobs.
    
    Returns:
        {
            "scheduler_running": bool,
            "jobs_count": int,
            "jobs": {
                "job_id": {
                    "id": str,
                    "name": str,
                    "next_run_time": datetime,
                    "trigger": str,
                    "func_name": str,
                    "max_instances": int
                }
            },
            "timestamp": datetime
        }
    """
    scheduler = get_scheduler()
    return scheduler.get_job_status()


@app.get("/api/v1/scheduler/health", tags=["Scheduler"])
async def scheduler_health():
    """
    Quick health check for the scheduler.
    
    Returns a simple boolean indicating if the scheduler is running.
    """
    scheduler = get_scheduler()
    return {
        "scheduler_running": scheduler.is_running,
        "timestamp": datetime.utcnow()
    }


# ============================================================================
# EXAMPLE ADDITIONAL ENDPOINTS
# ============================================================================

@app.get("/api/v1/scheduler/jobs", tags=["Scheduler"])
async def list_jobs():
    """
    List all scheduler jobs with details.
    
    Returns information about each scheduled job including
    next run time, trigger interval, and status.
    """
    scheduler = get_scheduler()
    status = scheduler.get_job_status()
    
    jobs_list = []
    for job_id, job_info in status["jobs"].items():
        jobs_list.append({
            "job_id": job_id,
            "name": job_info["name"],
            "interval": job_info["trigger"],
            "next_run": job_info["next_run_time"],
        })
    
    return {
        "scheduler_running": status["scheduler_running"],
        "total_jobs": status["jobs_count"],
        "jobs": jobs_list,
        "timestamp": status["timestamp"]
    }


@app.get("/api/v1/scheduler/job/{job_id}", tags=["Scheduler"])
async def get_job_details(job_id: str):
    """
    Get detailed information about a specific job.
    
    Parameters:
        job_id: The ID of the job (e.g., 'reservation_collector', 'shipping_collector')
    
    Returns:
        Job details including name, trigger, and next run time.
        Returns 404 if job not found.
    """
    scheduler = get_scheduler()
    status = scheduler.get_job_status()
    
    if job_id not in status["jobs"]:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    job_info = status["jobs"][job_id]
    return {
        "job_id": job_id,
        "details": job_info,
        "timestamp": status["timestamp"]
    }


# ============================================================================
# USAGE NOTES
# ============================================================================

"""
INTEGRATION STEPS:

1. Add this code to your app/api/main.py file

2. Make sure APScheduler is installed:
   pip install APScheduler

3. The scheduler will automatically start when the FastAPI app starts

4. Access scheduler status at:
   GET http://localhost:8000/api/v1/scheduler/status
   GET http://localhost:8000/api/v1/scheduler/health
   GET http://localhost:8000/api/v1/scheduler/jobs
   GET http://localhost:8000/api/v1/scheduler/job/{job_id}

CONFIGURATION:

You can modify the collector intervals in:
app/collectors/scheduler.py - CollectorScheduler.JOB_CONFIG

- ReservationCollector: interval_hours = 6
- ShippingCollector: interval_hours = 3

MONITORING:

All scheduler events are logged. Check your application logs for:
- Scheduler startup/shutdown messages
- Job execution events
- Any errors or exceptions

PRODUCTION CONSIDERATIONS:

1. Ensure your database connections handle concurrent access
2. Monitor the scheduler status endpoint for uptime
3. Configure appropriate logging levels
4. Consider using a task queue (Celery) for large-scale deployments
5. Set up alerts for scheduler failures
"""
