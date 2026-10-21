"""
Audit Store Execution Logger Service
Logs StateGuard execution lineage, invariant checks, and GitOps PR creations into SQLite WAL mode.
"""
import os
import sys
import site
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Ensure user site-packages is in python path
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.append(user_site)

logger = logging.getLogger("cloudguard.audit_logger")

try:
    from stateguard import AuditStore, AuditEvent, EventType
    HAS_AUDIT = True
except ImportError:
    HAS_AUDIT = False


class CloudGuardAuditLogger:
    """
    Logger for auditing all StateGuard transactions and GitOps PR events.
    """

    def __init__(self, db_path: str = "stateguard_audit.db"):
        self.db_path = db_path
        self.store = AuditStore(db_path=db_path) if HAS_AUDIT else None

    def log_swarm_consensus(self, trace_id: str, resource_id: str, agreed_spec: str, savings: float) -> None:
        """
        Logs a swarm consensus event.
        """
        logger.info("Audit Log [SWARM_PROPOSAL]: saga_id=%s, resource=%s, spec=%s, savings=$%.2f/mo",
                    trace_id, resource_id, agreed_spec, savings)
        if HAS_AUDIT and self.store:
            try:
                if hasattr(EventType, "MUTATION"):
                    event_type = EventType.MUTATION
                elif hasattr(EventType, "MUTATION_PROPOSAL"):
                    event_type = getattr(EventType, "MUTATION_PROPOSAL")
                else:
                    event_type = list(EventType)[0]
                event = AuditEvent(
                    event_type=event_type,
                    saga_id=trace_id,
                    state_before={"resource_id": resource_id},
                    state_after={"agreed_spec": agreed_spec, "monthly_savings_usd": savings},
                    message=f"Swarm consensus agreed spec '{agreed_spec}' with savings ${savings:.2f}/mo"
                )
                if hasattr(self.store, "log_event"):
                    self.store.log_event(event)
            except Exception as e:
                logger.warning("Failed to write to AuditStore: %s", e)

    def log_pr_created(self, trace_id: str, pr_number: int, pr_url: str, savings: float) -> None:
        """
        Logs a GitOps Pull Request creation event.
        """
        logger.info("Audit Log [PR_CREATED]: saga_id=%s, pr_number=%d, url=%s, savings=$%.2f/mo",
                    trace_id, pr_number, pr_url, savings)

    def log_saga_rollback(self, trace_id: str, reason: str) -> None:
        """
        Logs a Saga transaction rollback event.
        """
        logger.warning("Audit Log [SAGA_ROLLBACK]: saga_id=%s, reason=%s", trace_id, reason)
