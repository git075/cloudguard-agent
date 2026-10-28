"""
Celery Distributed Task Queue & Beat Scheduler Configuration for CloudGuard FinOps.
Provides asynchronous job dispatching, result backends, and scheduled nightly scans.
"""
import os
from celery import Celery
from celery.schedules import crontab

# Redis URLs from environment variables
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

celery_app = Celery(
    "cloudguard",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["src.jobs.scan_worker"],
)

# Celery Configuration
task_eager = os.getenv("TESTING") == "1" or os.getenv("CELERY_TASK_ALWAYS_EAGER") == "1"

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                     # Prevent message loss on worker crash
    task_reject_on_worker_lost=True,         # Re-queue task if worker process dies
    worker_prefetch_multiplier=1,            # Prevent task starvation on long scans
    task_soft_time_limit=3300,               # 55 mins soft limit (enables graceful cleanup)
    task_time_limit=3600,                    # 60 mins hard SIGKILL limit
    result_expires=86400,                    # 24h result backend TTL in Redis
    task_always_eager=task_eager,
    task_eager_propagates=True,
    # Configure Celery Beat schedule for automated nightly scans
    beat_schedule={
        "nightly-cloudguard-scan-all-tenants": {
            "task": "src.jobs.scan_worker.run_nightly_scans",
            "schedule": crontab(hour=0, minute=0),  # Runs every midnight UTC
        },
    },
)


if __name__ == "__main__":
    celery_app.start()
