"""
Unit Tests for Phase 3 StateGuard Governance Integration
Imports directly from PyPI stateguard-core library.
"""
import unittest
from stateguard import GuardedState, InvariantRegistry, InvariantViolation, DriftDetector, DriftViolation, Saga

from src.models.telemetry import ResourceTelemetry, TerraformResourceBlock
from src.agents.swarm_orchestrator import SwarmOrchestrator
from src.governance.invariants import get_default_cloudguard_registry
from src.governance.engine import CloudGuardGovernanceEngine


class TestStateGuardGovernance(unittest.TestCase):

    def setUp(self):
        self.sample_state = {
            "resource_id": "production_db",
            "current_spec": "db.r5.2xlarge",
            "proposed_spec": "db.r6g.xlarge",
            "peak_cpu_percent": 45.0,
            "peak_memory_used_gb": 21.0,
            "proposed_memory_gb": 32.0, # 32 GB >= 21 * 1.25 (26.25 GB)
            "storage_encrypted": True,
            "publicly_accessible": False,
            "monthly_savings_usd": 950.0,
        }

        self.telemetry = ResourceTelemetry(
            resource_id="production_db",
            resource_type="aws_db_instance",
            current_instance_type="db.r5.2xlarge",
            monthly_cost_usd=1400.00,
            cpu_max_percent=42.5,
            memory_min_free_mb=44032.0, # 43 GB free out of 64 GB
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

    def test_guarded_state_proxy_rollback(self):
        state = GuardedState({"balance": 100})
        state.begin()
        state["balance"] = 500  # Mutation inside transaction
        self.assertEqual(state["balance"], 500)
        
        state.rollback()  # Erase mutation
        self.assertEqual(state["balance"], 100)

    def test_invariant_registry_block_mode(self):
        registry = get_default_cloudguard_registry()
        
        # Valid state should pass with 0 errors
        results = registry.check(self.sample_state)
        self.assertIsNotNone(results)

        # Invalid state violating RAM buffer rule
        invalid_state = dict(self.sample_state)
        invalid_state["proposed_memory_gb"] = 4.0  # Dangerously low RAM!
        
        with self.assertRaises(InvariantViolation):
            registry.check(invalid_state)

    def test_drift_detector_anomaly(self):
        detector = DriftDetector()
        detector.watch("monthly_savings_usd", z_threshold=3.5, mode="block")

        # Seed baseline deltas
        state_before = {"monthly_savings_usd": 100.0}
        detector.check(state_before, {"monthly_savings_usd": 200.0}) # +100
        detector.check(state_before, {"monthly_savings_usd": 205.0}) # +105
        detector.check(state_before, {"monthly_savings_usd": 198.0}) # +98
        detector.check(state_before, {"monthly_savings_usd": 202.0}) # +102
        detector.check(state_before, {"monthly_savings_usd": 201.0}) # +101

        # Extreme anomaly ($50,000 savings spike -> Financial Hallucination)
        with self.assertRaises(DriftViolation):
            detector.check(state_before, {"monthly_savings_usd": 50100.0})

    def test_saga_compensation_lifo_order(self):
        execution_log = []

        def undo_step1():
            execution_log.append("undo_step1")

        def undo_step2():
            execution_log.append("undo_step2")

        state = GuardedState({"status": "init"})
        
        with self.assertRaises(ValueError):
            with Saga(state, saga_id="test_saga", raise_on_compensation_failure=False) as saga:
                saga.add_compensation(undo_step1, description="Undo step 1")
                saga.add_compensation(undo_step2, description="Undo step 2")
                raise ValueError("Simulated failure mid-step")

        # Must execute in LIFO order: step2 undo first, then step1 undo
        self.assertEqual(execution_log, ["undo_step2", "undo_step1"])

    def test_governance_engine_end_to_end(self):
        engine = CloudGuardGovernanceEngine()
        orchestrator = SwarmOrchestrator()

        result_state = engine.execute_governed_swarm(
            self.telemetry,
            self.resource_block,
            orchestrator.run_consensus_debate,
            baseline_cost_deltas=[900.0, 920.0, 940.0, 960.0]
        )

        self.assertEqual(result_state["status"], "committed")
        self.assertEqual(result_state["proposed_spec"], "db.r6g.xlarge")
        self.assertEqual(result_state["monthly_savings_usd"], 1104.0)  # $1400 - $296 (Phase 1+2)


    def test_negative_savings_invariant_violation(self):
        registry = get_default_cloudguard_registry()
        cost_increase_state = dict(self.sample_state)
        cost_increase_state["original_monthly_cost"] = 1000.0
        cost_increase_state["proposed_monthly_cost"] = 1500.0  # Cost Increase!
        cost_increase_state["monthly_savings_usd"] = -500.0
        with self.assertRaises(InvariantViolation):
            registry.check(cost_increase_state)

    def test_min_memory_floor_invariant_violation(self):
        registry = get_default_cloudguard_registry()
        low_memory_db_state = dict(self.sample_state)
        low_memory_db_state["resource_type"] = "aws_db_instance"
        low_memory_db_state["proposed_memory_gb"] = 2.0  # 2 GB < 4.0 GB DB floor!
        with self.assertRaises(InvariantViolation):
            registry.check(low_memory_db_state)

    def test_extreme_cost_drop_sanity_violation(self):
        registry = get_default_cloudguard_registry()
        extreme_drop_state = dict(self.sample_state)
        extreme_drop_state["original_monthly_cost"] = 10000.0
        extreme_drop_state["proposed_monthly_cost"] = 10.0  # 0.1% of original cost (Anomaly!)
        with self.assertRaises(InvariantViolation):
            registry.check(extreme_drop_state)

    def test_invalid_status_state_violation(self):
        registry = get_default_cloudguard_registry()
        corrupt_status_state = dict(self.sample_state)
        corrupt_status_state["status"] = "CORRUPTED_STATE"
        with self.assertRaises(InvariantViolation):
            registry.check(corrupt_status_state)

    def test_projected_cpu_headroom_invariant_violation(self):
        registry = get_default_cloudguard_registry()
        high_proj_cpu_state = dict(self.sample_state)
        high_proj_cpu_state["status"] = "proposed"
        high_proj_cpu_state["projected_cpu_percent"] = 85.0  # 85% > 80% ceiling!
        with self.assertRaises(InvariantViolation):
            registry.check(high_proj_cpu_state)

        # Safe projected CPU passes
        high_proj_cpu_state["projected_cpu_percent"] = 65.0
        self.assertIsNotNone(registry.check(high_proj_cpu_state))

    def test_db_connections_capacity_invariant_violation(self):
        registry = get_default_cloudguard_registry()
        db_conn_state = dict(self.sample_state)
        db_conn_state["resource_type"] = "aws_db_instance"
        db_conn_state["status"] = "proposed"
        db_conn_state["db_connections_max"] = 800
        db_conn_state["proposed_max_connections"] = 1000  # 800 > 700 (70% limit)
        with self.assertRaises(InvariantViolation):
            registry.check(db_conn_state)

        # Adequate capacity passes (800 <= 1400 * 0.7 = 980)
        db_conn_state["proposed_max_connections"] = 1400
        self.assertIsNotNone(registry.check(db_conn_state))

    def test_valid_catalog_instance_invariant_violation(self):
        registry = get_default_cloudguard_registry()
        invalid_spec_state = dict(self.sample_state)
        invalid_spec_state["status"] = "proposed"
        invalid_spec_state["proposed_spec"] = "db.nonexistent.superlarge"
        with self.assertRaises(InvariantViolation):
            registry.check(invalid_spec_state)

        # Valid catalog spec passes
        invalid_spec_state["proposed_spec"] = "db.r6g.xlarge"
        self.assertIsNotNone(registry.check(invalid_spec_state))

    def test_engine_architecture_compatibility_invariant_violation(self):
        registry = get_default_cloudguard_registry()
        oracle_arm_state = dict(self.sample_state)
        oracle_arm_state["resource_type"] = "aws_db_instance"
        oracle_arm_state["status"] = "proposed"
        oracle_arm_state["engine"] = "oracle-ee"
        oracle_arm_state["proposed_spec"] = "db.r6g.xlarge"  # Oracle cannot run on Graviton ARM!
        with self.assertRaises(InvariantViolation):
            registry.check(oracle_arm_state)

        # Postgres on ARM passes
        oracle_arm_state["engine"] = "postgres"
        self.assertIsNotNone(registry.check(oracle_arm_state))

    def test_ec2_architecture_lock_invariant_violation(self):
        registry = get_default_cloudguard_registry()
        x86_lock_state = dict(self.sample_state)
        x86_lock_state["resource_type"] = "aws_instance"
        x86_lock_state["status"] = "proposed"
        x86_lock_state["current_spec"] = "m5.2xlarge"
        x86_lock_state["proposed_spec"] = "m6g.xlarge"  # x86 -> ARM without permission!
        x86_lock_state["allow_arm_migration"] = False
        with self.assertRaises(InvariantViolation):
            registry.check(x86_lock_state)

        # Allowed ARM migration passes
        x86_lock_state["allow_arm_migration"] = True
        self.assertIsNotNone(registry.check(x86_lock_state))


if __name__ == "__main__":
    unittest.main()

