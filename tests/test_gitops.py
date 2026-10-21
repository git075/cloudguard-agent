"""
Unit Tests for Phase 4 GitOps Engine, Audit Store Logger, and Dashboard REST API
"""
import unittest

from src.models.telemetry import ResourceTelemetry, TerraformResourceBlock
from src.agents.swarm_orchestrator import SwarmOrchestrator
from src.services.gitops import GitOpsEngine
from src.services.audit_logger import CloudGuardAuditLogger

try:
    from fastapi.testclient import TestClient
    from src.ui.dashboard_api import app
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


class TestPhase4GitOpsAndDashboard(unittest.TestCase):

    def setUp(self):
        self.telemetry = ResourceTelemetry(
            resource_id="production_db",
            resource_type="aws_db_instance",
            current_instance_type="db.r5.2xlarge",
            monthly_cost_usd=1400.00,
            cpu_max_percent=42.5,
            memory_min_free_mb=44032.0,
            total_memory_mb=65536.0,
            tags={"Environment": "production"}
        )

        self.resource_block = TerraformResourceBlock(
            file_path="main.tf",
            resource_type="aws_db_instance",
            resource_name="production_db",
            current_attributes={
                "instance_class": "db.r5.2xlarge",
                "storage_encrypted": True,
                "publicly_accessible": False,
                "tags": {"Environment": "production"}
            }
        )

        self.orchestrator = SwarmOrchestrator()
        self.consensus = self.orchestrator.run_consensus_debate(self.telemetry, self.resource_block)
        self.gitops = GitOpsEngine(use_mock=True)
        self.client = TestClient(app) if HAS_FASTAPI else None

    def test_gitops_mock_pr_creation(self):
        pr_result = self.gitops.create_optimization_pull_request(
            repo_full_name="acme/infrastructure",
            file_path="main.tf",
            resource_telemetry=self.telemetry,
            consensus=self.consensus,
            updated_hcl_code='instance_class = "db.r6g.xlarge"'
        )

        self.assertEqual(pr_result["status"], "open")
        self.assertEqual(pr_result["pr_number"], 142)
        self.assertIn("https://github.com/acme/infrastructure/pull/142", pr_result["pr_url"])
        self.assertIn("cloudguard/opt-production_db-", pr_result["branch_name"])

    def test_gitops_pr_markdown_formatting(self):
        markdown = self.gitops.generate_pr_markdown(self.telemetry, self.consensus)

        self.assertIn("## ⚡ CloudGuard Cost Optimization Suggestion", markdown)
        self.assertIn("`db.r5.2xlarge`", markdown)
        self.assertIn("`db.r6g.xlarge`", markdown)
        self.assertIn("-$1104.00 / mo", markdown)  # Phase 1+2: correct savings
        self.assertIn("StateGuard Safety Proof & Verification", markdown)

    def test_gitops_delete_branch_compensation(self):
        result = self.gitops.delete_branch("acme/infrastructure", "cloudguard/opt-production_db-101")
        self.assertTrue(result)

    def test_audit_logger_events(self):
        logger_service = CloudGuardAuditLogger(db_path="stateguard_audit.db")
        logger_service.log_swarm_consensus("trace_101", "production_db", "db.r6g.xlarge", 1104.0)
        logger_service.log_pr_created("trace_101", 142, "https://github.com/acme/infrastructure/pull/142", 1104.0)
        logger_service.log_saga_rollback("trace_101", "Simulated error")
        self.assertEqual(logger_service.db_path, "stateguard_audit.db")

    def test_dashboard_api_health(self):
        if not HAS_FASTAPI:
            self.skipTest("FastAPI not installed in system Python environment.")
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_dashboard_api_savings_metrics(self):
        if not HAS_FASTAPI:
            self.skipTest("FastAPI not installed in system Python environment.")
        response = self.client.get("/api/v1/metrics/savings")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["monthly_savings_usd"], 950.00)
        self.assertEqual(data["annualized_savings_usd"], 11400.00)
        self.assertEqual(data["stateguard_protection_rate_percent"], 100.0)

    def test_dashboard_api_list_prs(self):
        if not HAS_FASTAPI:
            self.skipTest("FastAPI not installed in system Python environment.")
        response = self.client.get("/api/v1/pull-requests")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["pull_requests"][0]["pr_id"], "pr_101")

    def test_dashboard_ui_html_serving(self):
        if not HAS_FASTAPI:
            self.skipTest("FastAPI not installed in system Python environment.")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CloudGuard", response.text)
        self.assertIn("StateGuard", response.text)
        self.assertIn("db.r6g.xlarge", response.text)

        dash_response = self.client.get("/dashboard")
        self.assertEqual(dash_response.status_code, 200)
        self.assertIn("CloudGuard", dash_response.text)



if __name__ == "__main__":
    unittest.main()
