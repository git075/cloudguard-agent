"""
Unified CloudGuard Governance Engine
Powered 100% directly by PyPI stateguard-core: GuardedState, InvariantRegistry, DriftDetector, Saga, AuditStore, and NamespacedState.
"""
import sys
import site
import logging
from typing import Dict, Any, Callable, Optional, List

# Ensure user site-packages is in python path
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.append(user_site)

from stateguard import GuardedState, InvariantRegistry, DriftDetector, Saga, AuditStore, create_agent_state

from src.models.telemetry import ResourceTelemetry, TerraformResourceBlock
from src.models.swarm import SwarmConsensus
from src.governance.invariants import get_default_cloudguard_registry

logger = logging.getLogger("cloudguard.governance.engine")


class CloudGuardGovernanceEngine:
    """
    Unified Engine providing ACID-like state governance, agent memory isolation, and audit logging.
    Directly uses PyPI stateguard-core features: GuardedState, Invariants, Drift, Saga, Namespaces, and AuditStore.
    """

    def __init__(
        self,
        registry: Optional[InvariantRegistry] = None,
        drift_detector: Optional[DriftDetector] = None,
        audit_db_path: str = "stateguard_audit.db",
    ):
        self.registry = registry or get_default_cloudguard_registry()
        self.drift_detector = drift_detector or DriftDetector()
        self.drift_detector.watch("monthly_savings_usd", mode="block", z_threshold=3.5)
        self.audit_db_path = audit_db_path
        self.audit_store = AuditStore(db_path=audit_db_path)

    def create_isolated_agent_state(
        self,
        base_state: GuardedState,
        agent_id: str,
        shared_keys: Optional[List[str]] = None,
        is_orchestrator: bool = False,
    ):
        """
        Creates a namespaced isolated memory view for a specific agent (e.g. 'finops', 'arch', 'sec').
        """
        return create_agent_state(
            base_state=base_state,
            agent_id=agent_id,
            shared_keys=shared_keys or ["resource_id", "current_spec"],
            is_orchestrator=is_orchestrator,
        )

    def execute_governed_swarm(
        self,
        telemetry: ResourceTelemetry,
        resource_block: TerraformResourceBlock,
        swarm_func: Callable[[ResourceTelemetry, TerraformResourceBlock, GuardedState], SwarmConsensus],
        baseline_cost_deltas: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Executes swarm optimization inside a governed StateGuard Saga block.
        """
        # Extract engine, multi_az, and arm_migration flags
        engine_val = (
            getattr(telemetry, "engine", None)
            or resource_block.current_attributes.get("engine")
            or telemetry.tags.get("engine", "postgres")
        )
        is_multi_az = (
            getattr(telemetry, "multi_az", False)
            or resource_block.current_attributes.get("multi_az", False)
            or (str(telemetry.tags.get("multi_az", "")).lower() in ("true", "1"))
        )
        allow_arm = (
            resource_block.current_attributes.get("allow_arm_migration", False)
            or (str(telemetry.tags.get("allow_arm_migration", "")).lower() in ("true", "1"))
        )

        initial_state = {
            "resource_id": telemetry.resource_id,
            "resource_type": telemetry.resource_type,
            "current_spec": telemetry.current_instance_type,
            "proposed_spec": telemetry.current_instance_type,
            "original_monthly_cost": telemetry.monthly_cost_usd,
            "proposed_monthly_cost": telemetry.monthly_cost_usd,
            "monthly_savings_usd": 0.0,
            "peak_cpu_percent": telemetry.cpu_max_percent,
            "projected_cpu_percent": telemetry.cpu_max_percent,
            "db_connections_max": telemetry.db_connections_max,
            "proposed_max_connections": 10000,
            "engine": engine_val,
            "multi_az": is_multi_az,
            "allow_arm_migration": allow_arm,
            "peak_memory_used_gb": max(0.1, (telemetry.total_memory_mb - telemetry.memory_min_free_mb) / 1024.0),
            "proposed_memory_gb": telemetry.total_memory_mb / 1024.0,
            "storage_encrypted": resource_block.current_attributes.get("storage_encrypted", True),
            "publicly_accessible": resource_block.current_attributes.get("publicly_accessible", False),
            "status": "pending",
        }

        if baseline_cost_deltas:
            for delta in baseline_cost_deltas:
                self.drift_detector.observe("monthly_savings_usd", delta)

        guarded_state = GuardedState(initial_state)

        with Saga(guarded_state, registry=self.registry, saga_id=f"cloudguard_{telemetry.resource_id}") as saga:
            logger.info("Executing Governed Swarm optimization for resource '%s'...", telemetry.resource_id)

            state_before = guarded_state.to_dict()

            # Execute Swarm Consensus
            consensus: SwarmConsensus = swarm_func(telemetry, resource_block, guarded_state)

            from src.agents.finops_agent import INSTANCE_PRICING_CATALOG, calculate_projected_cpu
            spec_info = INSTANCE_PRICING_CATALOG.get(consensus.agreed_spec)

            # Mutate GuardedState with consensus outputs
            guarded_state["proposed_spec"] = consensus.agreed_spec
            guarded_state["proposed_monthly_cost"] = consensus.agreed_monthly_cost
            guarded_state["monthly_savings_usd"] = consensus.monthly_savings_usd
            guarded_state["projected_cpu_percent"] = calculate_projected_cpu(
                telemetry.current_instance_type, consensus.agreed_spec, telemetry.cpu_max_percent
            )

            if spec_info and "ram_gb" in spec_info:
                guarded_state["proposed_memory_gb"] = float(spec_info["ram_gb"])
                guarded_state["proposed_max_connections"] = int(spec_info.get("max_conn_rds", 0))
            else:
                # Safe fallback: parse size from spec string heuristically
                spec = consensus.agreed_spec.lower()
                if "8xlarge" in spec:
                    guarded_state["proposed_memory_gb"] = 256.0
                elif "4xlarge" in spec:
                    guarded_state["proposed_memory_gb"] = 128.0
                elif "2xlarge" in spec:
                    guarded_state["proposed_memory_gb"] = 64.0
                elif "xlarge" in spec:
                    guarded_state["proposed_memory_gb"] = 32.0
                elif "large" in spec:
                    guarded_state["proposed_memory_gb"] = 16.0
                elif "medium" in spec:
                    guarded_state["proposed_memory_gb"] = 4.0
                elif "small" in spec:
                    guarded_state["proposed_memory_gb"] = 2.0
                else:
                    guarded_state["proposed_memory_gb"] = 8.0  # Conservative default
                logger.warning(
                    "Spec '%s' not found in pricing catalog. Estimated RAM: %.1f GB (heuristic).",
                    consensus.agreed_spec, guarded_state["proposed_memory_gb"]
                )

            if consensus.is_approved:
                guarded_state["status"] = "proposed"
                state_after = guarded_state.to_dict()
                # Evaluate Statistical Drift Detector (stateguard-core PyPI syntax)
                self.drift_detector.check(state_before, state_after)
                # Observe valid savings to update rolling statistical baseline
                if consensus.monthly_savings_usd > 0:
                    self.drift_detector.observe("monthly_savings_usd", consensus.monthly_savings_usd)
                guarded_state["status"] = "committed"
                logger.info("Governed Swarm Execution PASSED all StateGuard safety checks.")
            else:
                guarded_state["status"] = "rejected"
                logger.info("Governed Swarm optimization REJECTED by swarm consensus.")

        return guarded_state.to_dict()
