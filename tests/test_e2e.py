"""
Comprehensive End-to-End Integration Test Suite for CloudGuard FinOps
Tests the complete lifecycle: AWS Telemetry Ingestion -> HCL Parsing -> Multi-Agent Swarm -> StateGuard Governance -> Code Mutation.
"""
import unittest
from stateguard import InvariantViolation, DriftViolation

from src.services.aws_collector import AWSMetricsCollector
from src.services.hcl_parser import TerraformHCLParser
from src.agents.swarm_orchestrator import SwarmOrchestrator
from src.governance.engine import CloudGuardGovernanceEngine
from src.models.telemetry import ResourceTelemetry, TerraformResourceBlock

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

SAMPLE_INSECURE_HCL = """
resource "aws_db_instance" "unencrypted_db" {
  allocated_storage   = 100
  engine              = "postgres"
  instance_class      = "db.r5.2xlarge"
  storage_encrypted   = false
  publicly_accessible = true
}
"""


class TestCloudGuardEndToEnd(unittest.TestCase):

    def setUp(self):
        self.collector = AWSMetricsCollector(use_mock=True)
        self.collector.initialize_session()
        self.parser = TerraformHCLParser()
        self.orchestrator = SwarmOrchestrator()
        self.engine = CloudGuardGovernanceEngine()

    def test_e2e_successful_optimization(self):
        """
        Tests full end-to-end execution where a production database is right-sized from
        db.r5.2xlarge ($1,400) to db.r6g.xlarge ($450), saving $950/mo cleanly.
        """
        # 1. Fetch AWS Telemetry
        telemetry = self.collector.fetch_resource_telemetry("production_db", "aws_db_instance")
        self.assertEqual(telemetry.current_instance_type, "db.r5.2xlarge")

        # 2. Parse HCL Code
        blocks = self.parser.parse_hcl_content("main.tf", SAMPLE_SECURE_HCL)
        self.assertEqual(len(blocks), 1)

        # 3. Execute Governed Swarm
        result_state = self.engine.execute_governed_swarm(
            telemetry=telemetry,
            resource_block=blocks[0],
            swarm_func=self.orchestrator.run_consensus_debate,
            baseline_cost_deltas=[900.0, 920.0, 940.0, 960.0]
        )

        self.assertEqual(result_state["status"], "committed")
        self.assertEqual(result_state["proposed_spec"], "db.r6g.xlarge")
        self.assertEqual(result_state["monthly_savings_usd"], 1104.0)   # $1400 - $296

        # 4. Mutate HCL Code
        mutation = self.parser.mutate_instance_spec(
            file_path="main.tf",
            content=SAMPLE_SECURE_HCL,
            resource_type=blocks[0].resource_type,
            resource_name=blocks[0].resource_name,
            attribute_name="instance_class",
            new_value=result_state["proposed_spec"]
        )

        self.assertIn('instance_class      = "db.r6g.xlarge"', mutation.updated_code)

    def test_e2e_ram_buffer_invariant_block_and_rollback(self):
        """
        Tests StateGuard InvariantRegistry blocks a transaction where proposed
        memory is below the 1.20x peak memory safety threshold.

        Mock swarm returns db.t4g.micro (1 GB RAM) as agreed_spec.
        Engine looks up db.t4g.micro in catalog → proposed_memory_gb = 1.0 GB.
        StateGuard invariant: 1.0 GB >= 21.0 * 1.20 = 25.2 GB → VIOLATION RAISED.
        """
        from src.models.swarm import FinOpsProposal, ArchReview, SecurityReview
        telemetry = self.collector.fetch_resource_telemetry("production_db", "aws_db_instance")
        blocks = self.parser.parse_hcl_content("main.tf", SAMPLE_SECURE_HCL)

        def dangerous_undersized_swarm_func(t, b, state):
            """
            Returns a consensus with agreed_spec='db.t4g.micro' (1 GB RAM).
            Engine resolves it to proposed_memory_gb=1.0 from the pricing catalog.
            StateGuard invariant: 1.0 GB < 21 GB peak * 1.20 = 25.2 GB → VIOLATION.
            """
            from src.models.swarm import SwarmConsensus
            fp = FinOpsProposal(
                resource_id=t.resource_id, current_spec=t.current_instance_type,
                proposed_spec="db.t4g.micro", current_monthly_cost=t.monthly_cost_usd,
                proposed_monthly_cost=14.0, estimated_savings_usd=1386.0,
                proposed_ram_gb=1.0, proposed_vcpu=2, rationale="Dangerously undersized",
            )
            return SwarmConsensus(
                resource_id=t.resource_id, original_spec=t.current_instance_type,
                agreed_spec="db.t4g.micro", original_monthly_cost=t.monthly_cost_usd,
                agreed_monthly_cost=14.0, monthly_savings_usd=1386.0, is_approved=True,
                finops_proposal=fp,
                arch_review=ArchReview(is_approved=True, requires_counter_proposal=False),
                security_review=SecurityReview(is_approved=True),
            )

        # StateGuard MUST raise InvariantViolation: 1.0 GB < 21.0 GB * 1.20 = 25.2 GB
        with self.assertRaises(InvariantViolation):
            self.engine.execute_governed_swarm(
                telemetry=telemetry,
                resource_block=blocks[0],
                swarm_func=dangerous_undersized_swarm_func,
                baseline_cost_deltas=[1380.0, 1390.0, 1385.0],
            )

    def test_e2e_security_compliance_audit_rejection(self):
        """
        Tests that an insecure database (unencrypted / publicly accessible) is rejected
        by the Security Agent and StateGuard governance.
        """
        telemetry = self.collector.fetch_resource_telemetry("unencrypted_db", "aws_db_instance")
        blocks = self.parser.parse_hcl_content("main.tf", SAMPLE_INSECURE_HCL)

        # Swarm debate must fail security audit
        consensus = self.orchestrator.run_consensus_debate(telemetry, blocks[0])
        self.assertFalse(consensus.is_approved)
        self.assertFalse(consensus.security_review.is_approved)

    def test_e2e_drift_anomaly_block_and_rollback(self):
        """
        Tests StateGuard DriftDetector Z-Score anomaly block when an LLM hallucinates an extreme cost delta.
        """
        telemetry = self.collector.fetch_resource_telemetry("production_db", "aws_db_instance")
        blocks = self.parser.parse_hcl_content("main.tf", SAMPLE_SECURE_HCL)

        # Seed baseline observations on DriftDetector watch
        watch = self.engine.drift_detector._watches.get("monthly_savings_usd")
        if watch:
            for d in [100.0, 105.0, 95.0, 102.0, 98.0]:
                watch.record_delta(abs(d))

        # Mock a hallucinated swarm function returning $50,000/mo savings
        def hallucinated_swarm_func(t, b, state):
            consensus = self.orchestrator.run_consensus_debate(t, b, state)
            consensus.monthly_savings_usd = 50000.0  # Hallucinated savings!
            return consensus

        with self.assertRaises(DriftViolation):
            self.engine.execute_governed_swarm(
                telemetry=telemetry,
                resource_block=blocks[0],
                swarm_func=hallucinated_swarm_func
            )


if __name__ == "__main__":
    unittest.main()
