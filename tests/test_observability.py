"""
Unit & Integration Tests for Phase 6 Observability (Prometheus, Structlog, Sentry).
"""
import pytest
from fastapi.testclient import TestClient

from src.ui.dashboard_api import app
from src.utils.metrics import (
    record_scan_metrics,
    record_pr_metrics,
    record_invariant_violation,
    get_prometheus_metrics_bytes,
)
from src.utils.logging import setup_logging, get_logger
from src.utils.monitoring import init_sentry, capture_exception


def test_prometheus_metrics_recording_and_endpoint():
    """Tests Prometheus metrics recording and the /metrics endpoint response."""
    # 1. Record sample metrics
    record_scan_metrics(status="completed", duration_sec=5.2, savings_usd=1104.0)
    record_pr_metrics(pr_type="single")
    record_invariant_violation(rule_name="ram_buffer")

    # 2. Fetch /metrics endpoint via TestClient
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    metrics_output = response.text

    assert "cloudguard_scan_jobs_total" in metrics_output
    assert "cloudguard_scan_savings_identified_usd_total" in metrics_output
    assert "cloudguard_pull_requests_created_total" in metrics_output
    assert "cloudguard_stateguard_invariant_violations_total" in metrics_output


def test_structured_json_logging(capsys):
    """Tests structlog JSON logging output formatting."""
    setup_logging(level="INFO", json_format=True)
    logger = get_logger("test_module")

    logger.info("Scan job completed", scan_job_id="job-123", savings_usd=1104.0)
    captured = capsys.readouterr()

    assert "Scan job completed" in captured.out
    assert "job-123" in captured.out
    assert "1104.0" in captured.out


def test_sentry_monitoring_no_op_fallback():
    """Tests Sentry SDK graceful fallback when DSN is not provided."""
    # Sentry DSN not set -> init should return False
    initialized = init_sentry(dsn="")
    assert initialized is False

    # Exception capture should execute without crashing
    try:
        raise ValueError("Test observability error")
    except ValueError as e:
        event_id = capture_exception(e, tags={"test": "true"})
        assert event_id is None or isinstance(event_id, str)
