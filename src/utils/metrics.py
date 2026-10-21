"""
Prometheus Observability & Metrics Module for CloudGuard FinOps.
Provides counters, histograms, and gauges to track scans, cost savings, PR creations, and StateGuard invariant blocks.
"""
import time
from typing import Callable
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)

# Custom Registry or Global REGISTRY
REGISTRY_OBJ = REGISTRY

# 1. Scan Job Counters & Metrics
SCAN_JOBS_TOTAL = Counter(
    "cloudguard_scan_jobs_total",
    "Total number of CloudGuard infrastructure scan jobs executed",
    ["status"],  # completed, failed, running
    registry=REGISTRY_OBJ,
)

SCAN_SAVINGS_IDENTIFIED_USD = Counter(
    "cloudguard_scan_savings_identified_usd_total",
    "Cumulative total monthly cost savings identified in USD",
    registry=REGISTRY_OBJ,
)

SCAN_DURATION_SECONDS = Histogram(
    "cloudguard_scan_duration_seconds",
    "Histogram of background scan job execution duration in seconds",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
    registry=REGISTRY_OBJ,
)

# 2. GitOps PR Metrics
PULL_REQUESTS_CREATED_TOTAL = Counter(
    "cloudguard_pull_requests_created_total",
    "Total number of Terraform GitOps pull requests created",
    ["pr_type"],  # single, batch
    registry=REGISTRY_OBJ,
)

# 3. StateGuard Invariant Violation Metrics
STATEGUARD_INVARIANT_VIOLATIONS_TOTAL = Counter(
    "cloudguard_stateguard_invariant_violations_total",
    "Total number of StateGuard safety invariant violations blocked",
    ["rule_name"],  # ram_buffer, cpu_max, drift_anomaly, security_audit
    registry=REGISTRY_OBJ,
)

# 4. System & Tenant Health Metrics
ACTIVE_TENANTS_COUNT = Gauge(
    "cloudguard_active_tenants_count",
    "Number of currently active customer tenant organizations",
    registry=REGISTRY_OBJ,
)


def record_scan_metrics(status: str, duration_sec: float, savings_usd: float = 0.0) -> None:
    """Helper to record scan job metrics in Prometheus."""
    SCAN_JOBS_TOTAL.labels(status=status).inc()
    SCAN_DURATION_SECONDS.observe(duration_sec)
    if savings_usd > 0:
        SCAN_SAVINGS_IDENTIFIED_USD.inc(savings_usd)


def record_pr_metrics(pr_type: str = "single") -> None:
    """Helper to record PR creation in Prometheus."""
    PULL_REQUESTS_CREATED_TOTAL.labels(pr_type=pr_type).inc()


def record_invariant_violation(rule_name: str) -> None:
    """Helper to record StateGuard invariant violations in Prometheus."""
    STATEGUARD_INVARIANT_VIOLATIONS_TOTAL.labels(rule_name=rule_name).inc()


def get_prometheus_metrics_bytes() -> bytes:
    """Returns encoded Prometheus metrics for the /metrics HTTP endpoint."""
    return generate_latest(REGISTRY_OBJ)
