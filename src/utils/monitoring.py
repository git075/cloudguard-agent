"""
Sentry Telemetry & Error Tracking Integration for CloudGuard FinOps.
Provides exception capture, performance tracing, and tenant-aware error monitoring.
"""
import os
import logging
from typing import Dict, Any, Optional

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

logger = logging.getLogger("cloudguard.monitoring")


def init_sentry(dsn: Optional[str] = None, environment: Optional[str] = None) -> bool:
    """
    Initializes Sentry SDK with integrations for FastAPI, Celery, and SQLAlchemy.
    Returns True if initialized, False if DSN is missing or disabled.
    """
    sentry_dsn = dsn or os.getenv("SENTRY_DSN")
    env = environment or os.getenv("ENVIRONMENT", "production")

    if not sentry_dsn:
        logger.info("Sentry DSN not provided. Error tracking running in NO-OP mode.")
        return False

    try:
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=env,
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2")),
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                CeleryIntegration(monitor_beat_tasks=True),
                SqlalchemyIntegration(),
            ],
        )
        logger.info("Sentry SDK initialized successfully for environment '%s'.", env)
        return True
    except Exception as exc:
        logger.warning("Failed to initialize Sentry SDK: %s", str(exc))
        return False


def capture_exception(
    exc: Exception, tags: Optional[Dict[str, str]] = None, extra: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Captures an exception and sends it to Sentry with custom tenant tags and context.
    """
    if tags:
        for k, v in tags.items():
            sentry_sdk.set_tag(k, v)

    if extra:
        for k, v in extra.items():
            sentry_sdk.set_extra(k, v)

    event_id = sentry_sdk.capture_exception(exc)
    logger.error("Captured exception sent to Sentry (Event ID: %s): %s", event_id, str(exc))
    return event_id
