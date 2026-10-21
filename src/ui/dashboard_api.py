"""
FastAPI Dashboard REST API Endpoints
Feeds Next.js glassmorphism frontend with active PRs, savings metrics, and StateGuard audit traces.
"""
import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, status

from src.models.telemetry import ResourceTelemetry
from src.services.aws_collector import AWSMetricsCollector
from src.services.hcl_parser import TerraformHCLParser
from src.agents.swarm_orchestrator import SwarmOrchestrator
from src.governance.engine import CloudGuardGovernanceEngine
from src.services.gitops import GitOpsEngine

logger = logging.getLogger("cloudguard.dashboard_api")

app = FastAPI(
    title="CloudGuard FinOps API",
    description="Autonomous Multi-Agent GitOps Cloud Cost Optimization Engine powered by StateGuard",
    version="0.1.0"
)

# Shared In-Memory Log Store for Demo API
PR_STORE: List[Dict[str, Any]] = [
    {
        "pr_id": "pr_101",
        "github_pr_url": "https://github.com/acme/infrastructure/pull/42",
        "resource_id": "aws_db_instance.main_db",
        "old_instance_type": "db.r5.2xlarge",
        "new_instance_type": "db.r6g.xlarge",
        "monthly_savings_usd": 950.00,
        "status": "open",
        "stateguard_status": "passed_all_invariants"
    }
]


from pathlib import Path
from fastapi.responses import HTMLResponse, Response
from src.utils.metrics import get_prometheus_metrics_bytes, CONTENT_TYPE_LATEST
from src.api.auth_router import router as auth_router
from src.api.scan_router import router as scan_router

# Include API Routers
app.include_router(auth_router)
app.include_router(scan_router)

STATIC_INDEX_PATH = Path(__file__).parent / "static" / "index.html"


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the CloudGuard FinOps Executive Glassmorphism Dashboard."""
    if STATIC_INDEX_PATH.exists():
        return HTMLResponse(content=STATIC_INDEX_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>CloudGuard Dashboard: static/index.html not found</h2>")


@app.get("/api/v1/health", status_code=status.HTTP_200_OK)
def health_check() -> Dict[str, Any]:
    """
    Service health check endpoint.
    """
    return {"status": "healthy", "service": "CloudGuard FinOps", "version": "0.1.0"}



@app.get("/metrics")
def prometheus_metrics() -> Response:
    """
    Exposes Prometheus metrics for monitoring scrapers.
    """
    return Response(content=get_prometheus_metrics_bytes(), media_type=CONTENT_TYPE_LATEST)



@app.get("/api/v1/metrics/savings", status_code=status.HTTP_200_OK)
def get_savings_metrics() -> Dict[str, Any]:
    """
    Returns total annualized savings and active PR metrics for dashboard header widgets.
    """
    total_monthly = sum(item["monthly_savings_usd"] for item in PR_STORE if item["status"] == "open")
    return {
        "active_prs_count": len(PR_STORE),
        "monthly_savings_usd": total_monthly,
        "annualized_savings_usd": total_monthly * 12.0,
        "stateguard_protection_rate_percent": 100.0
    }


@app.get("/api/v1/pull-requests", status_code=status.HTTP_200_OK)
def list_pull_requests() -> Dict[str, Any]:
    """
    Returns list of active CloudGuard Pull Requests.
    """
    return {
        "total": len(PR_STORE),
        "pull_requests": PR_STORE
    }
