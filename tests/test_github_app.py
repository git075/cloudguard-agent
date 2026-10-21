"""
Unit & Integration Tests for GitHub App RS256 Auth & Multi-Resource Batch PR Generation.
"""
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from src.models.swarm import FinOpsProposal, ArchReview, SecurityReview, SwarmConsensus
from src.models.telemetry import ResourceTelemetry
from src.services.github_app import GitHubAppAuth
from src.services.gitops import GitOpsEngine


@pytest.fixture
def sample_rsa_private_key_pem():
    """Generates an in-memory RSA 2048 private key in PEM format for test signing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


def test_github_app_jwt_generation(sample_rsa_private_key_pem):
    """Tests RS256 JWT creation using RSA private key."""
    auth = GitHubAppAuth(
        app_id="123456",
        private_key_pem=sample_rsa_private_key_pem,
        use_mock=False,
    )
    jwt_token = auth.generate_app_jwt()

    assert isinstance(jwt_token, str)
    assert len(jwt_token) > 50


def test_github_app_mock_installation_token():
    """Tests mock installation access token retrieval."""
    auth = GitHubAppAuth(use_mock=True)
    token_data = auth.get_installation_access_token(installation_id="inst-999")

    assert "token" in token_data
    assert token_data["token"] == "ghs_mock_installation_token_inst-999"
    assert token_data["permissions"]["pull_requests"] == "write"


def test_multi_resource_batch_pr_generation():
    """Tests generating a unified batch PR for multiple resource right-sizings."""
    engine = GitOpsEngine(use_mock=True)

    tel1 = ResourceTelemetry(
        resource_id="production_db",
        resource_type="aws_db_instance",
        current_instance_type="db.r5.2xlarge",
        monthly_cost_usd=1400.0,
        cpu_max_percent=45.0,
        cpu_avg_percent=12.0,
        memory_min_free_mb=32768.0,
        total_memory_mb=65536.0,
    )
    fin1 = FinOpsProposal(
        resource_id="production_db",
        current_spec="db.r5.2xlarge",
        proposed_spec="db.r6g.xlarge",
        current_monthly_cost=1400.0,
        proposed_monthly_cost=296.0,
        estimated_savings_usd=1104.0,
        proposed_ram_gb=32.0,
        proposed_vcpu=4,
        rationale="Right-size to Graviton r6g.xlarge",
    )
    arch1 = ArchReview(is_approved=True, requires_counter_proposal=False, rationale="RAM buffer safe")
    sec1 = SecurityReview(is_approved=True, rationale="Encryption verified")

    con1 = SwarmConsensus(
        resource_id="production_db",
        original_spec="db.r5.2xlarge",
        agreed_spec="db.r6g.xlarge",
        original_monthly_cost=1400.0,
        agreed_monthly_cost=296.0,
        monthly_savings_usd=1104.0,
        is_approved=True,
        finops_proposal=fin1,
        arch_review=arch1,
        security_review=sec1,
        debate_trace=["FinOps: Propose db.r6g.xlarge", "Arch: Approved"],
    )

    tel2 = ResourceTelemetry(
        resource_id="analytics_db",
        resource_type="aws_db_instance",
        current_instance_type="db.r5.xlarge",
        monthly_cost_usd=700.0,
        cpu_max_percent=30.0,
        cpu_avg_percent=8.0,
        memory_min_free_mb=16384.0,
        total_memory_mb=32768.0,
    )
    fin2 = FinOpsProposal(
        resource_id="analytics_db",
        current_spec="db.r5.xlarge",
        proposed_spec="db.m6g.xlarge",
        current_monthly_cost=700.0,
        proposed_monthly_cost=250.0,
        estimated_savings_usd=450.0,
        proposed_ram_gb=16.0,
        proposed_vcpu=4,
        rationale="Right-size to Graviton m6g.xlarge",
    )
    arch2 = ArchReview(is_approved=True, requires_counter_proposal=False, rationale="RAM buffer safe")
    sec2 = SecurityReview(is_approved=True, rationale="Encryption verified")

    con2 = SwarmConsensus(
        resource_id="analytics_db",
        original_spec="db.r5.xlarge",
        agreed_spec="db.m6g.xlarge",
        original_monthly_cost=700.0,
        agreed_monthly_cost=250.0,
        monthly_savings_usd=450.0,
        is_approved=True,
        finops_proposal=fin2,
        arch_review=arch2,
        security_review=sec2,
        debate_trace=["FinOps: Propose db.m6g.xlarge", "Arch: Approved"],
    )

    mutations = [
        {
            "file_path": "terraform/rds.tf",
            "resource_telemetry": tel1,
            "consensus": con1,
            "updated_hcl_code": 'resource "aws_db_instance" "prod" { instance_class = "db.r6g.xlarge" }',
        },
        {
            "file_path": "terraform/analytics.tf",
            "resource_telemetry": tel2,
            "consensus": con2,
            "updated_hcl_code": 'resource "aws_db_instance" "analytics" { instance_class = "db.m6g.xlarge" }',
        },
    ]

    res = engine.create_batch_optimization_pull_request(
        repo_full_name="acme/infrastructure",
        mutations=mutations,
    )

    assert res["status"] == "open"
    assert res["mutations_count"] == 2
    assert res["total_monthly_savings_usd"] == 1554.0
    assert "production_db" in res["markdown_body"]
    assert "analytics_db" in res["markdown_body"]
    assert "$1554.00 / month" in res["markdown_body"]
