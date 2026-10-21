"""
Unit Tests for Phase 2 Multi-Agent Swarm Integration
"""
import unittest
from src.models.telemetry import ResourceTelemetry, TerraformResourceBlock
from src.models.swarm import FinOpsProposal
from src.agents.finops_agent import FinOpsAgent
from src.agents.arch_agent import ArchitectureAgent
from src.agents.security_agent import SecurityAgent
from src.agents.swarm_orchestrator import SwarmOrchestrator



class TestMultiAgentSwarm(unittest.TestCase):

    def setUp(self):
        # 43 GB free out of 64 GB -> Peak RAM used = 21 GB. Required with 25% buffer = 26.25 GB (fits db.r6g.xlarge with 32 GB)
        self.rds_telemetry = ResourceTelemetry(
            resource_id="production_db",
            resource_type="aws_db_instance",
            current_instance_type="db.r5.2xlarge",
            monthly_cost_usd=1400.00,
            cpu_max_percent=42.5,
            memory_min_free_mb=44032.0, # 43 GB free
            total_memory_mb=65536.0,   # 64 GB total
            tags={"Environment": "production", "Owner": "devops"}
        )

        self.valid_resource_block = TerraformResourceBlock(
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

    def test_finops_agent_proposal(self):
        """
        Phase 1+2 Production: FinOps agent now uses constraint-based optimal selector.
        Peak RAM = 21 GB (43 GB free / 64 GB total). Required RAM with 1.10x buffer = 23.1 GB.
        The cheapest instance satisfying 23.1 GB RAM is db.r6g.xlarge (32 GB, $296/mo, Graviton).
        The old hardcoded db.t4g.large (8 GB) is correctly excluded due to insufficient RAM.
        """
        agent = FinOpsAgent()
        proposal = agent.propose_optimization(self.rds_telemetry)

        self.assertEqual(proposal.resource_id, "production_db")
        self.assertEqual(proposal.current_spec, "db.r5.2xlarge")
        self.assertEqual(proposal.proposed_spec, "db.r6g.xlarge")   # Smart selector result
        self.assertEqual(proposal.proposed_monthly_cost, 296.00)     # Real Graviton pricing
        self.assertEqual(proposal.estimated_savings_usd, 1104.00)    # $1400 - $296 = $1104
        self.assertEqual(proposal.proposed_ram_gb, 32.0)             # db.r6g.xlarge has 32 GB
        self.assertTrue("Graviton" in proposal.rationale)            # Graviton upgrade mentioned

    def test_arch_agent_approves_good_finops_proposal(self):
        """
        Phase 1+2: FinOps now directly proposes db.r6g.xlarge (32 GB RAM).
        Peak RAM used = 21 GB. Required with 1.25x Arch buffer = 26.25 GB.
        db.r6g.xlarge (32 GB) >= 26.25 GB → Arch agent APPROVES directly.
        No counter-proposal needed because FinOps chose correctly.
        """
        finops = FinOpsAgent()
        arch = ArchitectureAgent()

        proposal = finops.propose_optimization(self.rds_telemetry)
        # New smart FinOps proposes db.r6g.xlarge (32 GB) which satisfies arch requirements
        review = arch.evaluate_proposal(self.rds_telemetry, proposal)

        self.assertTrue(review.is_approved)             # Arch approves directly
        self.assertFalse(review.requires_counter_proposal)  # No counter-proposal needed
        self.assertAlmostEqual(review.peak_memory_used_gb, 21.0, delta=0.5)

    def test_security_agent_audit_success(self):
        sec = SecurityAgent()
        review = sec.audit_resource_block(self.valid_resource_block)

        self.assertTrue(review.is_approved)
        self.assertEqual(len(review.violations), 0)

    def test_security_agent_audit_failure(self):
        sec = SecurityAgent()
        unencrypted_block = TerraformResourceBlock(
            file_path="main.tf",
            resource_type="aws_db_instance",
            resource_name="unencrypted_db",
            current_attributes={
                "storage_encrypted": False, # Violation!
                "publicly_accessible": True, # Violation!
                "tags": {} # Missing Environment tag!
            }
        )
        review = sec.audit_resource_block(unencrypted_block)

        self.assertFalse(review.is_approved)
        self.assertEqual(len(review.violations), 3)

    def test_swarm_orchestrator_end_to_end_debate(self):
        """
        Phase 1+2: Smart FinOps proposes db.r6g.xlarge ($296/mo) directly.
        Arch Agent approves (32 GB > 26.25 GB required). Security Agent approves.
        Consensus on FinOps proposal: $1400 - $296 = $1104 savings.
        """
        orchestrator = SwarmOrchestrator()
        consensus = orchestrator.run_consensus_debate(
            self.rds_telemetry,
            self.valid_resource_block
        )

        self.assertTrue(consensus.is_approved)
        self.assertEqual(consensus.agreed_spec, "db.r6g.xlarge")
        self.assertEqual(consensus.agreed_monthly_cost, 296.00)    # Real Graviton pricing
        self.assertEqual(consensus.monthly_savings_usd, 1104.00)   # $1400 - $296
        self.assertGreater(len(consensus.debate_trace), 2)          # Has debate trace


    def test_arch_agent_corrupt_telemetry_rejection(self):
        arch = ArchitectureAgent()
        finops = FinOpsAgent()
        corrupt_telemetry = ResourceTelemetry(
            resource_id="corrupt_db",
            resource_type="aws_db_instance",
            current_instance_type="db.r5.2xlarge",
            monthly_cost_usd=1400.00,
            cpu_max_percent=42.5,
            memory_min_free_mb=70000.0,  # 70 GB free > 64 GB total (IMPOSSIBLE/CORRUPT!)
            total_memory_mb=65536.0,
        )
        proposal = finops.propose_optimization(corrupt_telemetry)
        with self.assertRaises(ValueError):
            arch.evaluate_proposal(corrupt_telemetry, proposal)

    def test_arch_agent_high_cpu_rejection(self):
        arch = ArchitectureAgent()
        finops = FinOpsAgent()
        high_cpu_telemetry = ResourceTelemetry(
            resource_id="high_cpu_db",
            resource_type="aws_db_instance",
            current_instance_type="db.r5.2xlarge",
            monthly_cost_usd=1400.00,
            cpu_max_percent=88.0,  # 88% > 80% max CPU threshold!
            memory_min_free_mb=44032.0,
            total_memory_mb=65536.0,
        )
        proposal = finops.propose_optimization(high_cpu_telemetry)
        review = arch.evaluate_proposal(high_cpu_telemetry, proposal)
        self.assertFalse(review.is_approved)
        self.assertFalse(review.requires_counter_proposal)
        self.assertIn("exceeds max threshold", review.rationale)

    def test_security_agent_missing_encryption_attribute_failure(self):
        sec = SecurityAgent()
        missing_encryption_block = TerraformResourceBlock(
            file_path="main.tf",
            resource_type="aws_db_instance",
            resource_name="missing_enc_db",
            current_attributes={
                "publicly_accessible": False,
                "tags": {"Environment": "production"}
                # storage_encrypted is MISSING!
            }
        )
        review = sec.audit_resource_block(missing_encryption_block)
        self.assertFalse(review.is_approved)
        self.assertIn("Storage encryption ('storage_encrypted') is missing or disabled.", review.violations)

    def test_finops_agent_core_collapse_prevention(self):
        """
        Tests that FinOps Agent avoids downsizing an 8-vCPU instance to a 2-vCPU or 4-vCPU instance
        when peak CPU utilization is high (70%), even if RAM usage is tiny (5.5 GB).
        A naive RAM-only selector would pick db.m6g.large (2 vCPU) causing a 233% CPU crash.
        Our multi-metric selector picks db.r6g.2xlarge (8 vCPUs) to maintain safe compute capacity.
        """
        agent = FinOpsAgent()
        high_cpu_low_ram_telemetry = ResourceTelemetry(
            resource_id="compute_intensive_db",
            resource_type="aws_db_instance",
            current_instance_type="db.r5.2xlarge",  # 8 vCPUs, 64 GB RAM, $749/mo
            monthly_cost_usd=1400.00,
            cpu_max_percent=70.0,                   # High compute: 5.6 active cores!
            memory_min_free_mb=60000.0,             # Tiny RAM used: only ~5.4 GB
            total_memory_mb=65536.0,
            tags={"Environment": "production"}
        )
        proposal = agent.propose_optimization(high_cpu_low_ram_telemetry)

        # Must propose an 8-vCPU instance (db.m6g.2xlarge), NOT db.r6g.large (2 vCPU) or db.r6g.xlarge (4 vCPU)
        self.assertEqual(proposal.proposed_spec, "db.m6g.2xlarge")
        self.assertEqual(proposal.proposed_vcpu, 8)
        self.assertIn("Projected peak CPU utilization", proposal.rationale)

    def test_arch_agent_joint_multi_metric_counter_proposal(self):
        """
        Tests that Arch Agent detects when a proposed spec has sufficient RAM but suffers
        from projected CPU saturation, rejecting the proposal and dynamically counter-proposing
        a safe spec from the catalog.
        """
        arch = ArchitectureAgent()
        high_cpu_telemetry = ResourceTelemetry(
            resource_id="db_with_high_cpu",
            resource_type="aws_db_instance",
            current_instance_type="db.r5.2xlarge",  # 8 vCPUs, 64 GB RAM
            monthly_cost_usd=1400.00,
            cpu_max_percent=72.0,                   # Active cores = 5.76
            memory_min_free_mb=50000.0,             # Peak RAM used = 15.1 GB
            total_memory_mb=65536.0,
        )
        # Aggressive proposal: only 2 vCPUs and 16 GB RAM (RAM buffer satisfied, but projected CPU > 200%)
        unsafe_proposal = FinOpsProposal(
            resource_id="db_with_high_cpu",
            current_spec="db.r5.2xlarge",
            proposed_spec="db.r6g.large",          # 2 vCPUs, 16 GB RAM -> Unsafe CPU!
            current_monthly_cost=1400.00,
            proposed_monthly_cost=148.00,
            estimated_savings_usd=1252.00,
            proposed_ram_gb=16.0,
            proposed_vcpu=2,
            rationale="Aggressive downsize",
        )
        review = arch.evaluate_proposal(high_cpu_telemetry, unsafe_proposal)

        self.assertFalse(review.is_approved)
        self.assertTrue(review.requires_counter_proposal)
        self.assertIn("projected CPU saturation", review.rationale)
        # Must counter-propose a tier with enough vCPUs and RAM (db.m6g.2xlarge has 8 vCPUs, 32 GB RAM)
        self.assertEqual(review.counter_proposed_spec, "db.m6g.2xlarge")

    def test_swarm_two_way_consensus_negotiation(self):
        """
        Tests full end-to-end swarm debate where Arch Agent issues a safe dynamic counter-proposal
        and the Swarm Orchestrator adopts it through two-way negotiation.
        """
        # Configure Arch Agent with stricter 1.6x RAM buffer (21 GB * 1.6 = 33.6 GB)
        # FinOps proposes db.r6g.xlarge (32 GB) -> Arch rejects & counter-proposes db.r6g.2xlarge (64 GB)
        arch_agent = ArchitectureAgent(ram_safety_buffer_ratio=1.6)
        orchestrator = SwarmOrchestrator(arch_agent=arch_agent)

        consensus = orchestrator.run_consensus_debate(self.rds_telemetry, self.valid_resource_block)

        self.assertTrue(consensus.is_approved)
        self.assertEqual(consensus.agreed_spec, "db.r6g.2xlarge")
        self.assertEqual(consensus.agreed_monthly_cost, 592.00)
        self.assertEqual(consensus.monthly_savings_usd, 808.00)
        self.assertTrue(any("Consensus Negotiated" in step for step in consensus.debate_trace))

    def test_finops_agent_oracle_graviton_exclusion(self):
        """
        Tests that FinOps Agent avoids Graviton (r6g/m6g) for Oracle/SQL Server engines,
        and selects an Intel x86 spec (db.r5.xlarge) instead.
        """
        agent = FinOpsAgent()
        oracle_telemetry = ResourceTelemetry(
            resource_id="oracle_production_db",
            resource_type="aws_db_instance",
            engine="oracle-ee",
            current_instance_type="db.r5.2xlarge",
            monthly_cost_usd=1400.00,
            cpu_max_percent=30.0,
            memory_min_free_mb=40000.0,  # ~24.9 GB used -> needs >= 27.4 GB
            total_memory_mb=65536.0,
            tags={"Environment": "production"}
        )
        proposal = agent.propose_optimization(oracle_telemetry)

        # Must NOT be db.r6g.xlarge ($296) because Oracle cannot run on Graviton
        self.assertEqual(proposal.proposed_spec, "db.r5.xlarge")
        self.assertEqual(proposal.proposed_monthly_cost, 374.00)
        self.assertIn("Engine 'oracle-ee' requires x86_64 architecture", proposal.rationale)

    def test_finops_agent_ec2_x86_lock_prevention(self):
        """
        Tests that an EC2 x86 instance (m5.2xlarge) is not migrated to ARM (m6g.xlarge)
        unless explicitly allowed via allow_arm_migration tag.
        """
        agent = FinOpsAgent()
        x86_ec2_telemetry = ResourceTelemetry(
            resource_id="app_server_ec2",
            resource_type="aws_instance",
            current_instance_type="m5.2xlarge",  # 32 GB RAM, 8 vCPUs, $280/mo
            monthly_cost_usd=280.00,
            cpu_max_percent=25.0,
            memory_min_free_mb=20000.0,          # ~12.5 GB used -> needs >= 13.7 GB
            total_memory_mb=32768.0,
            tags={"Environment": "production"}   # No allow_arm_migration tag
        )
        proposal = agent.propose_optimization(x86_ec2_telemetry)

        # Must select m5.xlarge ($140), NOT m6g.xlarge ($112)
        self.assertEqual(proposal.proposed_spec, "m5.xlarge")
        self.assertEqual(proposal.proposed_monthly_cost, 140.00)
        self.assertIn("x86_64 AMI lock", proposal.rationale)

        # Now enable allow_arm_migration tag
        x86_ec2_telemetry.tags["allow_arm_migration"] = "true"
        arm_proposal = agent.propose_optimization(x86_ec2_telemetry)
        self.assertEqual(arm_proposal.proposed_spec, "m6g.xlarge")
        self.assertEqual(arm_proposal.proposed_monthly_cost, 112.00)

    def test_finops_agent_multi_az_pricing_multiplier(self):
        """
        Tests that Multi-AZ database instances apply the 2.0x cost multiplier
        to both current cost calculations and proposed catalog costs.
        """
        agent = FinOpsAgent()
        multi_az_telemetry = ResourceTelemetry(
            resource_id="multi_az_postgres_db",
            resource_type="aws_db_instance",
            engine="postgres",
            multi_az=True,
            current_instance_type="db.r5.2xlarge",
            monthly_cost_usd=2000.00,
            cpu_max_percent=30.0,
            memory_min_free_mb=40000.0,
            total_memory_mb=65536.0,
            tags={"Environment": "production"}
        )
        proposal = agent.propose_optimization(multi_az_telemetry)

        # Base db.r6g.xlarge is $296/mo. With Multi-AZ 2x, it must be $592/mo.
        self.assertEqual(proposal.proposed_spec, "db.r6g.xlarge")
        self.assertEqual(proposal.proposed_monthly_cost, 592.00)
        self.assertEqual(proposal.estimated_savings_usd, 1408.00)
        self.assertIn("Multi-AZ pricing applied (2x Single-AZ baseline)", proposal.rationale)


if __name__ == "__main__":
    unittest.main()


