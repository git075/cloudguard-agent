"""
Comprehensive End-to-End System Audit Test Suite.
Verifies:
1. Every UI Screen & User Interaction Contract (Login, Register, Dashboard, AWS Modal, Theme Switching).
2. Every Backend API Feature & Multi-Tenant Database Isolation.
3. Every End-to-End Multi-Agent Swarm & StateGuard Governance Flow.
4. Comprehensive Security & Penetration Hardening (JWT tampering, SQLi defense, IAM ARN injection, Confused Deputy defense, Invariant safety floors).
"""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from stateguard import InvariantViolation, DriftViolation

from src.ui.dashboard_api import app, STATIC_INDEX_PATH, STATIC_LOGIN_PATH
from src.db.session import get_async_db
from src.models.db import Base, Customer, AWSAccount, ScanJob
from src.services.auth import (
    create_access_token,
    decode_access_token,
    generate_external_id,
    hash_password,
    verify_password,
)
from src.models.telemetry import ResourceTelemetry, TerraformResourceBlock
from src.services.aws_collector import AWSMetricsCollector
from src.services.hcl_parser import TerraformHCLParser
from src.agents.swarm_orchestrator import SwarmOrchestrator
from src.governance.engine import CloudGuardGovernanceEngine
from src.governance.invariants import get_default_cloudguard_registry


SAMPLE_SECURE_HCL = """
resource "aws_db_instance" "production_db" {
  allocated_storage   = 500
  engine              = "postgres"
  instance_class      = "db.r5.2xlarge"
  storage_encrypted   = true
  publicly_accessible = false

  tags = {
    Environment = "production"
    Owner       = "devops"
  }
}
"""


# --- Test Fixtures ---

@pytest.fixture
def test_engine():
    """In-memory SQLite async database engine for testing."""
    return create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def async_audit_session(test_engine):
    """Provides an isolated database session with full schema initialized."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await test_engine.dispose()


@pytest.fixture
def api_client(async_audit_session):
    """Configures TestClient for FastAPI app with overridden DB session."""
    async def override_get_db():
        yield async_audit_session

    app.dependency_overrides[get_async_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ==============================================================================
# SECTION 1: UI SCREENS & INTERACTION CONTRACT TESTING
# ==============================================================================

class TestUIScreensAndInteractions:
    """Verifies that each UI view renders properly and contains all expected enterprise components."""

    def test_login_screen_html_rendering_and_elements(self, api_client):
        """Verifies /login and /register serve login.html with all required DOM elements and client scripts."""
        for path in ["/login", "/register"]:
            res = api_client.get(path)
            assert res.status_code == 200
            assert "text/html" in res.headers["content-type"]
            html = res.text

            # Page Title and Brand
            assert "CloudGuard FinOps" in html
            assert "Enterprise Workspace Sign In" in html

            # Mode Switch Tabs
            assert 'id="tab-login"' in html
            assert 'id="tab-register"' in html
            assert "setAuthMode('login')" in html
            assert "setAuthMode('register')" in html

            # Form Fields
            assert 'id="input-email"' in html
            assert 'id="input-password"' in html
            assert 'id="input-name"' in html
            assert 'id="btn-submit"' in html
            assert 'id="btn-submit-text"' in html

            # Status and Alert Containers
            assert 'id="auth-error-box"' in html
            assert 'id="auth-success-box"' in html

            # Client JS storage keys and redirects
            assert "localStorage.setItem('cloudguard_token'" in html
            assert "localStorage.setItem('cloudguard_customer_id'" in html
            assert "localStorage.setItem('cloudguard_external_id'" in html
            assert "window.location.href = '/dashboard'" in html

    def test_dashboard_screen_html_rendering_and_elements(self, api_client):
        """Verifies /dashboard and / serve index.html with all Cockpit widgets and controls."""
        for path in ["/", "/dashboard"]:
            res = api_client.get(path)
            assert res.status_code == 200
            assert "text/html" in res.headers["content-type"]
            html = res.text

            # Header Context
            assert 'id="header-tenant-name"' in html
            assert 'id="header-account-name"' in html
            assert 'id="auth-session-pill"' in html
            assert 'id="theme-toggle-btn"' in html
            assert 'id="btn-scan"' in html

            # Metric Cards
            assert "2,041.67" in html
            assert "24,500.00" in html
            assert "100% Passed" in html
            assert "Active Rules" in html

            # Candidate Cards Queue
            assert 'id="card-production_db"' in html
            assert 'id="card-analytics_warehouse"' in html
            assert 'id="card-api_gateway"' in html

            # Inspector Tabs & Panels
            assert 'id="inspector-panel-evidence"' in html
            assert 'id="inspector-panel-diff"' in html
            assert 'id="inspector-panel-policies"' in html
            assert 'id="btn-merge-action"' in html

            # AWS Access Modal
            assert 'id="aws-modal"' in html
            assert 'id="modal-external-id"' in html
            assert 'id="modal-iam-arn"' in html
            assert 'id="modal-account-alias"' in html
            assert 'id="connected-accounts-list"' in html
            assert 'id="btn-save-aws"' in html

            # Client Functions
            assert "function initTheme()" in html
            assert "function toggleEnterpriseTheme()" in html
            assert "function initAuth()" in html
            assert "function signOut()" in html
            assert "function loadConnectedAWSAccounts()" in html
            assert "function saveAWSAccount()" in html
            assert "function triggerAutonomousScan()" in html
            assert "function selectCandidate(" in html
            assert "function dispatchMergeAction()" in html

    def test_ui_theme_tokens_and_styling(self):
        """Verifies that CSS tokens support both Corporate Console (Light) and Neutral Charcoal (Dark)."""
        html = STATIC_INDEX_PATH.read_text(encoding="utf-8")
        
        # Base Console tokens
        assert "--canvas: #F8FAFC;" in html
        assert "--surface: #FFFFFF;" in html
        assert "--border-subtle: #E2E8F0;" in html
        assert "--accent: #2563EB;" in html

        # Neutral Charcoal tokens
        assert "html.theme-dark {" in html
        assert "--canvas: #09090B;" in html
        assert "--surface: #141417;" in html
        assert "--surface-elevated: #1F1F23;" in html


# ==============================================================================
# SECTION 2: BACKEND FEATURES & API TESTING
# ==============================================================================

class TestBackendFeaturesAndAPIs:
    """Verifies all FastAPI routes, JWT lifecycles, and database operations."""

    def test_tenant_registration_and_login_flow(self, api_client):
        """Test complete registration, login, and profile retrieval flow."""
        # 1. Register new tenant
        reg_payload = {
            "name": "Wayne Enterprises",
            "email": "bruce@waynecorp.com",
            "password": "BatMobileSecret2026!",
        }
        reg_res = api_client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_res.status_code == 201
        reg_data = reg_res.json()
        assert "access_token" in reg_data
        assert isinstance(reg_data["customer_id"], str)
        assert len(reg_data["customer_id"]) > 10
        assert reg_data["email"] == "bruce@waynecorp.com"
        assert reg_data["external_id"].startswith("cg_ext_")

        token = reg_data["access_token"]
        cust_id = reg_data["customer_id"]
        ext_id = reg_data["external_id"]

        # 2. Login with credentials
        login_res = api_client.post(
            "/api/v1/auth/login",
            json={"email": "bruce@waynecorp.com", "password": "BatMobileSecret2026!"},
        )
        assert login_res.status_code == 200
        login_data = login_res.json()
        assert login_data["access_token"] is not None
        assert login_data["customer_id"] == cust_id
        assert login_data["external_id"] == ext_id

        # 3. Retrieve /api/v1/auth/me profile
        headers = {"Authorization": f"Bearer {token}"}
        me_res = api_client.get("/api/v1/auth/me", headers=headers)
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["name"] == "Wayne Enterprises"
        assert me_data["email"] == "bruce@waynecorp.com"
        assert me_data["external_id"] == ext_id

    def test_aws_account_connection_and_listing(self, api_client):
        """Test connecting AWS IAM Role ARNs and listing them per customer tenant."""
        # Register customer
        reg_res = api_client.post(
            "/api/v1/auth/register",
            json={"name": "Cyberdyne Systems", "email": "miles@cyberdyne.com", "password": "SkynetPassword123!"},
        )
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Connect AWS account
        role_arn = "arn:aws:iam::987654321098:role/CloudGuardReadOnlyRole"
        conn_res = api_client.post(
            "/api/v1/accounts/aws",
            headers=headers,
            json={"role_arn": role_arn, "alias": "Cyberdyne Production US-West"},
        )
        assert conn_res.status_code == 201
        conn_data = conn_res.json()
        assert conn_data["account_id"] == "987654321098"
        assert conn_data["alias"] == "Cyberdyne Production US-West"

        # List connected accounts
        list_res = api_client.get("/api/v1/accounts/aws", headers=headers)
        assert list_res.status_code == 200
        accounts = list_res.json()
        assert len(accounts) == 1
        assert accounts[0]["account_id"] == "987654321098"

    def test_scan_trigger_unauthenticated_demo_vs_authenticated(self, api_client):
        """Test scan trigger in both unauthenticated (instant sandbox demo) and authenticated modes."""
        # 1. Unauthenticated demo scan trigger
        demo_res = api_client.post("/api/v1/scans/trigger")
        assert demo_res.status_code == 202
        demo_data = demo_res.json()
        assert demo_data["scan_job_id"] == "demo-scan-job"
        assert "Demo governed scan completed" in demo_data["message"]

        # 2. Authenticated scan trigger without accounts returns 404
        reg_res = api_client.post(
            "/api/v1/auth/register",
            json={"name": "Umbrella Corp", "email": "wesker@umbrella.com", "password": "T-VirusPassword123!"},
        )
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        empty_res = api_client.post("/api/v1/scans/trigger", headers=headers)
        assert empty_res.status_code == 404
        assert "No active AWS accounts found" in empty_res.json()["detail"]

    def test_dashboard_metrics_and_pull_requests(self, api_client):
        """Test dashboard summary metrics and pull request query endpoints."""
        # Health check
        h_res = api_client.get("/api/v1/health")
        assert h_res.status_code == 200
        assert h_res.json()["status"] == "healthy"

        # Metrics savings
        m_res = api_client.get("/api/v1/metrics/savings")
        assert m_res.status_code == 200
        m_data = m_res.json()
        assert m_data["active_prs_count"] >= 0
        assert m_data["monthly_savings_usd"] >= 0.0
        assert m_data["stateguard_protection_rate_percent"] == 100.0

        # Pull requests
        pr_res = api_client.get("/api/v1/pull-requests")
        assert pr_res.status_code == 200
        assert pr_res.json()["total"] >= 0

        # Prometheus metrics export
        pm_res = api_client.get("/metrics")
        assert pm_res.status_code == 200
        assert b"cloudguard_" in pm_res.content


# ==============================================================================
# SECTION 3: END-TO-END MULTI-AGENT SWARM & STATEGUARD FLOWS
# ==============================================================================

class TestEndToEndSwarmAndGovernanceFlows:
    """Tests the full multi-agent consensus, invariant validation, drift detection, and saga rollbacks."""

    def test_e2e_successful_rightsizing_flow(self):
        """Simulates full autonomous flow: Telemetry -> Consensus Debate -> StateGuard Invariants -> HCL Mutation."""
        collector = AWSMetricsCollector(use_mock=True)
        collector.initialize_session()
        telemetry = collector.fetch_resource_telemetry("production_db", "aws_db_instance")

        parser = TerraformHCLParser()
        blocks = parser.parse_hcl_content("rds.tf", SAMPLE_SECURE_HCL)
        assert len(blocks) == 1

        orchestrator = SwarmOrchestrator()
        engine = CloudGuardGovernanceEngine()

        result = engine.execute_governed_swarm(
            telemetry=telemetry,
            resource_block=blocks[0],
            swarm_func=orchestrator.run_consensus_debate,
            baseline_cost_deltas=[900.0, 920.0, 940.0, 960.0],
        )

        assert result["status"] == "committed"
        assert result["proposed_spec"] == "db.r6g.xlarge"
        assert result["monthly_savings_usd"] == 1104.0

        # Mutate Terraform HCL
        mutated = parser.mutate_instance_spec(
            file_path="rds.tf",
            content=SAMPLE_SECURE_HCL,
            resource_type=blocks[0].resource_type,
            resource_name=blocks[0].resource_name,
            attribute_name="instance_class",
            new_value=result["proposed_spec"],
        )
        assert 'instance_class      = "db.r6g.xlarge"' in mutated.updated_code
        assert "storage_encrypted   = true" in mutated.updated_code

    def test_e2e_drift_anomaly_rejection_and_saga_compensation(self):
        """Simulates an anomalous cost spike/drop causing drift rejection and rollback."""
        collector = AWSMetricsCollector(use_mock=True)
        collector.initialize_session()
        telemetry = collector.fetch_resource_telemetry("production_db", "aws_db_instance")

        parser = TerraformHCLParser()
        blocks = parser.parse_hcl_content("rds.tf", SAMPLE_SECURE_HCL)

        engine = CloudGuardGovernanceEngine()
        orchestrator = SwarmOrchestrator()

        # Seed baseline observations on DriftDetector watch
        watch = engine.drift_detector._watches.get("monthly_savings_usd")
        if watch:
            for d in [100.0, 105.0, 95.0, 102.0, 98.0]:
                watch.record_delta(abs(d))

        # Mock a hallucinated swarm function returning $50,000/mo savings
        def hallucinated_swarm_func(t, b, state):
            consensus = orchestrator.run_consensus_debate(t, b, state)
            consensus.monthly_savings_usd = 50000.0
            return consensus

        with pytest.raises(DriftViolation):
            engine.execute_governed_swarm(
                telemetry=telemetry,
                resource_block=blocks[0],
                swarm_func=hallucinated_swarm_func,
            )

    def test_e2e_security_invariant_rejection(self):
        """Simulates a security violation (e.g. unencrypted database storage) causing consensus rejection."""
        collector = AWSMetricsCollector(use_mock=True)
        collector.initialize_session()
        telemetry = collector.fetch_resource_telemetry("unencrypted_db", "aws_db_instance")

        insecure_hcl = (
            'resource "aws_db_instance" "unencrypted_db" {\n'
            '  instance_class = "db.r5.2xlarge"\n'
            '  storage_encrypted = false\n'
            '  publicly_accessible = true\n'
            '}'
        )
        parser = TerraformHCLParser()
        blocks = parser.parse_hcl_content("rds.tf", insecure_hcl)

        orchestrator = SwarmOrchestrator()
        consensus = orchestrator.run_consensus_debate(telemetry, blocks[0])
        assert consensus.is_approved is False
        assert consensus.security_review.is_approved is False


# ==============================================================================
# SECTION 4: SECURITY & PENETRATION HARDENING TESTS
# ==============================================================================

class TestSecurityAndPenetrationHardening:
    """Tests security controls: JWT tampering, SQLi, IAM injection, Confused Deputy defense, Invariant safety."""

    def test_jwt_tampering_and_algorithm_none_rejection(self):
        """Verifies that tampered JWT signatures, malformed tokens, and alg=none attacks are strictly rejected."""
        valid_token = create_access_token("cust_12345", "test@acme.com")
        
        # 1. Tampered payload
        parts = valid_token.split(".")
        tampered_token = f"{parts[0]}.eyJzdWIiOiAiaGFja2VyIn0.{parts[2]}"
        with pytest.raises(ValueError):
            decode_access_token(tampered_token)

        # 2. Arbitrary invalid string
        with pytest.raises(ValueError):
            decode_access_token("malformed.token.string")

        # 3. Algorithm 'none' attack payload
        fake_none_token = "eyJhbGciOiAibm9uZSIgfQ.eyJzdWIiOiAiY3VzdF8xMjM0NSJ9."
        with pytest.raises(ValueError):
            decode_access_token(fake_none_token)

    def test_sql_injection_defense_in_auth_endpoint(self, api_client):
        """Verifies that SQL injection attempts in login fields do not bypass auth or crash the database."""
        sqli_payloads = [
            "admin' OR '1'='1",
            "test@acme.com' UNION SELECT * FROM customers;--",
            "'; DROP TABLE customers;--",
        ]

        for payload in sqli_payloads:
            res = api_client.post(
                "/api/v1/auth/login",
                json={"email": payload, "password": "AnyPassword123!"},
            )
            # Rejected either by Pydantic schema validation (422) or Auth validation (401)
            assert res.status_code in (401, 422)

    def test_iam_role_arn_injection_defense(self, api_client):
        """Verifies that malicious, malformed, and non-conforming IAM Role ARNs are rejected by account router."""
        reg_res = api_client.post(
            "/api/v1/auth/register",
            json={"name": "Defense Corp", "email": "secops@defense.com", "password": "DefensePassword123!"},
        )
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        malicious_arns = [
            "arn:aws:iam::123456789012:role/../../root",
            "arn:aws:iam::12345:role/ShortAccountId",
            "arn:aws:iam::1234567890123:role/LongAccountId",
            "arn:aws:iam::123456789012:role/$(cat /etc/passwd)",
            "not-an-arn",
            "arn:aws:s3:::my-bucket",
            "arn:aws:iam::123456789012:user/Alice",
        ]

        for arn in malicious_arns:
            res = api_client.post("/api/v1/accounts/aws", headers=headers, json={"role_arn": arn})
            assert res.status_code == 400
            assert "Invalid IAM Role ARN format" in res.json()["detail"]

    def test_strict_multi_tenant_data_isolation(self, api_client):
        """Verifies that Tenant A cannot access, view, or scan against Tenant B's connected AWS accounts."""
        # Create Tenant A
        res_a = api_client.post(
            "/api/v1/auth/register",
            json={"name": "Tenant A", "email": "admin@tenant-a.com", "password": "PasswordA123!"},
        )
        token_a = res_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Create Tenant B
        res_b = api_client.post(
            "/api/v1/auth/register",
            json={"name": "Tenant B", "email": "admin@tenant-b.com", "password": "PasswordB123!"},
        )
        token_b = res_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant A registers an AWS Account
        conn_res = api_client.post(
            "/api/v1/accounts/aws",
            headers=headers_a,
            json={"role_arn": "arn:aws:iam::111111111111:role/CloudGuardReadOnlyRole", "alias": "Tenant A Account"},
        )
        acc_id_a = conn_res.json()["id"]

        # 1. Tenant B listing accounts must NOT see Tenant A's account
        list_b = api_client.get("/api/v1/accounts/aws", headers=headers_b)
        assert len(list_b.json()) == 0

        # 2. Tenant B attempting to trigger a scan using Tenant A's account ID must fail with 404
        hijack_scan = api_client.post(
            "/api/v1/scans/trigger",
            headers=headers_b,
            json={"aws_account_id": acc_id_a},
        )
        assert hijack_scan.status_code == 404
        assert "not found for this customer tenant" in hijack_scan.json()["detail"]

    def test_confused_deputy_external_id_defense(self):
        """Verifies that each customer generates a high-entropy ExternalId for STS AssumeRole condition."""
        ext1 = generate_external_id()
        ext2 = generate_external_id()

        assert ext1.startswith("cg_ext_")
        assert ext2.startswith("cg_ext_")
        assert ext1 != ext2
        assert len(ext1) >= 60

        # Validate that AWSMetricsCollector integrates external_id in STS parameters
        collector = AWSMetricsCollector(role_arn="arn:aws:iam::123456789012:role/CloudGuard", external_id=ext1, use_mock=True)
        assert collector.external_id == ext1

    def test_invariant_adversarial_rejections(self):
        """Exhaustively tests StateGuard Invariant rules against adversarial/poisoned inputs."""
        registry = get_default_cloudguard_registry()

        # Invariant 1: Negative Savings
        with pytest.raises(InvariantViolation):
            registry.check({
                "resource_type": "aws_db_instance",
                "current_spec": "db.r5.2xlarge",
                "proposed_spec": "db.r5.4xlarge",
                "original_monthly_cost": 500.0,
                "proposed_monthly_cost": 1000.0,
                "monthly_savings_usd": -500.0,
                "storage_encrypted": True,
                "publicly_accessible": False,
                "peak_cpu_percent": 30.0,
                "proposed_memory_gb": 64.0,
                "peak_memory_used_gb": 10.0,
                "status": "proposed"
            })

        # Invariant 2: Memory floor violation (< 1.25x headroom)
        with pytest.raises(InvariantViolation):
            registry.check({
                "resource_type": "aws_db_instance",
                "current_spec": "db.r5.2xlarge",
                "proposed_spec": "db.t4g.small",
                "original_monthly_cost": 1400.0,
                "proposed_monthly_cost": 200.0,
                "monthly_savings_usd": 1200.0,
                "storage_encrypted": True,
                "publicly_accessible": False,
                "peak_cpu_percent": 30.0,
                "proposed_memory_gb": 10.0,
                "peak_memory_used_gb": 10.0,
                "status": "proposed"
            })

        # Invariant 3: Hallucinated / Non-existent Catalog spec
        with pytest.raises(InvariantViolation):
            registry.check({
                "resource_type": "aws_db_instance",
                "current_spec": "db.r5.2xlarge",
                "proposed_spec": "ai.superfast.infinite",
                "original_monthly_cost": 1400.0,
                "proposed_monthly_cost": 200.0,
                "monthly_savings_usd": 1200.0,
                "storage_encrypted": True,
                "publicly_accessible": False,
                "peak_cpu_percent": 30.0,
                "proposed_memory_gb": 32.0,
                "peak_memory_used_gb": 10.0,
                "status": "proposed"
            })

        # Invariant 4: EC2 architecture lock (x86 to ARM without explicit permission)
        with pytest.raises(InvariantViolation):
            registry.check({
                "resource_type": "aws_instance",
                "current_spec": "m5.large",
                "proposed_spec": "t4g.large",
                "original_monthly_cost": 200.0,
                "proposed_monthly_cost": 100.0,
                "monthly_savings_usd": 100.0,
                "storage_encrypted": True,
                "publicly_accessible": False,
                "peak_cpu_percent": 30.0,
                "proposed_memory_gb": 8.0,
                "peak_memory_used_gb": 2.0,
                "allow_arm_migration": False,
                "status": "proposed"
            })

        # Valid Spec passes all 13 rules
        eval_result = registry.check({
            "resource_type": "aws_db_instance",
            "current_spec": "db.r5.2xlarge",
            "proposed_spec": "db.r6g.xlarge",
            "original_monthly_cost": 1400.0,
            "proposed_monthly_cost": 296.0,
            "monthly_savings_usd": 1104.0,
            "storage_encrypted": True,
            "publicly_accessible": False,
            "peak_cpu_percent": 42.5,
            "projected_cpu_percent": 70.8,
            "proposed_memory_gb": 32.0,
            "peak_memory_used_gb": 21.0,
            "db_connections_max": 200,
            "proposed_max_connections": 2630,
            "status": "proposed"
        })
        assert isinstance(eval_result, list)
        assert all(r.is_valid for r in eval_result)
