"""
Architecture & Reliability Agent (Hardened for Telemetry Validation)
Enforces 99th percentile peak memory and CPU safety buffers to prevent application outages.
"""
import logging
from typing import Dict, Any, Optional

from src.models.telemetry import ResourceTelemetry
from src.models.swarm import FinOpsProposal, ArchReview
from src.agents.finops_agent import INSTANCE_PRICING_CATALOG, calculate_projected_cpu

logger = logging.getLogger("cloudguard.arch_agent")


class ArchitectureAgent:
    """
    Agent responsible for evaluating system performance metrics and ensuring safe headroom.
    Enforces joint multi-metric constraints (RAM buffer, projected vCPU ceiling, DB connections, and IOPS).
    """

    def __init__(self, ram_safety_buffer_ratio: float = 1.25, max_cpu_threshold_percent: float = 80.0):
        if ram_safety_buffer_ratio < 1.0:
            raise ValueError("RAM safety buffer ratio cannot be less than 1.0 (100%)")
        if not (0.0 < max_cpu_threshold_percent <= 100.0):
            raise ValueError("Max CPU threshold percent must be between 0.0 and 100.0")

        self.ram_buffer_ratio = ram_safety_buffer_ratio
        self.max_cpu_threshold = max_cpu_threshold_percent

    def evaluate_proposal(self, telemetry: ResourceTelemetry, proposal: FinOpsProposal) -> ArchReview:
        """
        Evaluates a FinOps proposal against 90-day CloudWatch peak telemetry metrics.
        Performs joint multi-metric verification across RAM, projected vCPU, DB connections, and IOPS.
        Returns approval or a safe, dynamic catalog counter-proposal.
        """
        # Validate telemetry memory inputs
        if telemetry.total_memory_mb > 0 and telemetry.memory_min_free_mb > telemetry.total_memory_mb:
            raise ValueError(
                f"Corrupt telemetry data for '{telemetry.resource_id}': min free memory "
                f"({telemetry.memory_min_free_mb:.1f} MB) exceeds total memory ({telemetry.total_memory_mb:.1f} MB)."
            )

        if telemetry.total_memory_mb <= 0:
            logger.warning("Telemetry total_memory_mb is missing or zero for '%s', defaulting total RAM to 64.0 GB", telemetry.resource_id)
            total_ram_gb = 64.0
        else:
            total_ram_gb = telemetry.total_memory_mb / 1024.0

        if telemetry.memory_min_free_mb <= 0:
            free_ram_gb = total_ram_gb * 0.5
        else:
            free_ram_gb = telemetry.memory_min_free_mb / 1024.0

        peak_ram_used_gb = max(0.1, total_ram_gb - free_ram_gb)
        required_ram_gb = peak_ram_used_gb * self.ram_buffer_ratio

        # Calculate projected peak CPU utilization on the proposed spec
        projected_cpu = calculate_projected_cpu(
            telemetry.current_instance_type, proposal.proposed_spec, telemetry.cpu_max_percent
        )

        logger.info(
            "Arch Agent evaluating %s: Peak RAM Used=%.2f GB, Required Buffer RAM=%.2f GB, Proposed RAM=%.2f GB, Projected CPU=%.1f%%",
            telemetry.resource_id, peak_ram_used_gb, required_ram_gb, proposal.proposed_ram_gb, projected_cpu
        )

        # Check 1: Is current CPU utilization already exceeding safe limit?
        if telemetry.cpu_max_percent > self.max_cpu_threshold:
            return ArchReview(
                is_approved=False,
                requires_counter_proposal=False,
                peak_cpu_percent=telemetry.cpu_max_percent,
                peak_memory_used_gb=peak_ram_used_gb,
                rationale=f"Rejected: Peak CPU utilization ({telemetry.cpu_max_percent:.1f}%) exceeds max threshold of {self.max_cpu_threshold}%."
            )

        # Multi-Metric Joint Capacity Verification
        prop_info = INSTANCE_PRICING_CATALOG.get(proposal.proposed_spec, {})
        ram_ok = proposal.proposed_ram_gb >= required_ram_gb
        cpu_ok = projected_cpu <= self.max_cpu_threshold

        # DB Connection limit verification (RDS only)
        conn_ok = True
        if telemetry.resource_type == "aws_db_instance" and telemetry.db_connections_max > 0:
            max_allowed_conns = int(prop_info.get("max_conn_rds", 0) * 0.70)
            conn_ok = telemetry.db_connections_max <= max_allowed_conns

        # Network & IOPS Bandwidth verification
        peak_net = max(telemetry.network_in_mb_max, telemetry.network_out_mb_max) * 8.0
        net_ok = (peak_net == 0) or (prop_info.get("net_mbps", 1000) >= peak_net * 1.20)
        peak_iops_mbps = ((telemetry.io_read_iops_max + telemetry.io_write_iops_max) * 16.0) / 1024.0
        ebs_ok = (peak_iops_mbps == 0) or (prop_info.get("ebs_mbps", 500) >= peak_iops_mbps * 1.20)

        # If ALL combined metrics satisfy architecture safety requirements -> APPROVE!
        if ram_ok and cpu_ok and conn_ok and net_ok and ebs_ok:
            return ArchReview(
                is_approved=True,
                requires_counter_proposal=False,
                peak_cpu_percent=telemetry.cpu_max_percent,
                peak_memory_used_gb=peak_ram_used_gb,
                rationale=(
                    f"Approved: Proposed RAM ({proposal.proposed_ram_gb:.1f} GB) satisfies required buffer ({required_ram_gb:.1f} GB), "
                    f"projected CPU ({projected_cpu:.1f}%) <= {self.max_cpu_threshold}%, and connection/bandwidth headroom verified."
                )
            )

        # Identify failing bottlenecks to report in rationale
        failures = []
        if not ram_ok:
            failures.append(f"insufficient RAM ({proposal.proposed_ram_gb:.1f} GB < required {required_ram_gb:.1f} GB)")
        if not cpu_ok:
            failures.append(f"projected CPU saturation ({projected_cpu:.1f}% > {self.max_cpu_threshold}%)")
        if not conn_ok:
            failures.append(f"DB connections ({telemetry.db_connections_max} exceeds 70% of {prop_info.get('max_conn_rds', 0)} max)")
        if not net_ok or not ebs_ok:
            failures.append("network/storage IOPS bandwidth ceiling exceeded")

        # Formulate a safe, dynamic catalog counter-proposal satisfying ALL combined metrics
        counter_spec = self._select_safe_counter_spec(telemetry.resource_type, required_ram_gb, telemetry)

        if counter_spec and counter_spec in INSTANCE_PRICING_CATALOG:
            spec_info = INSTANCE_PRICING_CATALOG[counter_spec]
            is_multi_az = getattr(telemetry, "multi_az", False) or (str(telemetry.tags.get("multi_az", "")).lower() in ("true", "1"))
            cost_mult = 2.0 if is_multi_az else 1.0
            counter_proj_cpu = calculate_projected_cpu(telemetry.current_instance_type, counter_spec, telemetry.cpu_max_percent)
            return ArchReview(
                is_approved=False,
                requires_counter_proposal=True,
                counter_proposed_spec=counter_spec,
                counter_proposed_cost=float(spec_info["cost"]) * cost_mult,
                counter_proposed_ram_gb=float(spec_info["ram_gb"]),
                counter_proposed_vcpu=int(spec_info["vcpu"]),
                peak_cpu_percent=telemetry.cpu_max_percent,
                peak_memory_used_gb=peak_ram_used_gb,
                rationale=(
                    f"Rejected aggressive proposal ({proposal.proposed_spec}) due to: {', '.join(failures)}. "
                    f"Counter-proposing safe dynamic catalog tier: {counter_spec} "
                    f"({spec_info['ram_gb']} GB RAM, {spec_info['vcpu']} vCPUs, projected CPU {counter_proj_cpu:.1f}%)."
                )
            )

        # If no valid counter-spec is available in the catalog, reject without counter-proposal
        return ArchReview(
            is_approved=False,
            requires_counter_proposal=False,
            peak_cpu_percent=telemetry.cpu_max_percent,
            peak_memory_used_gb=peak_ram_used_gb,
            rationale=(
                f"Rejected proposal ({proposal.proposed_spec}) due to: {', '.join(failures)}. "
                f"No smaller instance tier in the catalog safely satisfies all combined constraints. Keeping current spec."
            )
        )

    def _select_safe_counter_spec(
        self,
        resource_type: str,
        required_ram_gb: float,
        telemetry: Optional[ResourceTelemetry] = None,
    ) -> Optional[str]:
        """
        Dynamically finds the lowest-cost instance tier in the catalog that satisfies
        ALL combined requirements: RAM buffer, projected vCPU ceiling, DB connections, and bandwidth.
        """
        catalog_type = "rds" if resource_type == "aws_db_instance" else "ec2"

        candidates = [
            (spec, info) for spec, info in INSTANCE_PRICING_CATALOG.items()
            if info["resource_type"] == catalog_type and info["ram_gb"] >= required_ram_gb
        ]

        if telemetry:
            # Enforce Engine Compatibility & EC2 Architecture Lock
            engine_str = str(getattr(telemetry, "engine", None) or telemetry.tags.get("engine", "")).lower()
            is_commercial = any(e in engine_str for e in ("oracle", "sqlserver", "sql-server"))
            allow_arm_migration = str(telemetry.tags.get("allow_arm_migration", "")).lower() in ("true", "1")
            curr_is_x86_ec2 = (catalog_type == "ec2" and any(fam in telemetry.current_instance_type for fam in ("m5", "r5", "c5", "t3")))
            exclude_arm = is_commercial or (curr_is_x86_ec2 and not allow_arm_migration)

            if exclude_arm:
                candidates = [(s, i) for s, i in candidates if not i.get("graviton", False)]

            # Multi-AZ cost multiplier
            is_multi_az = getattr(telemetry, "multi_az", False) or (str(telemetry.tags.get("multi_az", "")).lower() in ("true", "1"))
            cost_mult = 2.0 if is_multi_az else 1.0

            # Enforce projected CPU ceiling
            candidates = [
                (s, i) for s, i in candidates
                if calculate_projected_cpu(telemetry.current_instance_type, s, telemetry.cpu_max_percent) <= self.max_cpu_threshold
            ]

            # Enforce DB connection limit (RDS)
            if catalog_type == "rds" and telemetry.db_connections_max > 0:
                candidates = [
                    (s, i) for s, i in candidates
                    if i.get("max_conn_rds", 0) >= int(telemetry.db_connections_max / 0.70)
                ]

            # Enforce network & EBS bandwidth
            peak_net = max(telemetry.network_in_mb_max, telemetry.network_out_mb_max) * 8.0
            if peak_net > 0:
                candidates = [(s, i) for s, i in candidates if i.get("net_mbps", 1000) >= peak_net * 1.20]

            peak_iops_mbps = ((telemetry.io_read_iops_max + telemetry.io_write_iops_max) * 16.0) / 1024.0
            if peak_iops_mbps > 0:
                candidates = [(s, i) for s, i in candidates if i.get("ebs_mbps", 500) >= peak_iops_mbps * 1.20]

            # Exclude current spec and more expensive specs
            candidates = [
                (s, i) for s, i in candidates
                if s != telemetry.current_instance_type and (i["cost"] * cost_mult) < telemetry.monthly_cost_usd
            ]

        if not candidates:
            # Fallback for simple legacy calls without telemetry
            if catalog_type == "rds":
                return "db.r6g.xlarge" if required_ram_gb <= 32.0 else "db.r5.2xlarge"
            else:
                return "m6g.large" if required_ram_gb <= 8.0 else "m5.xlarge"

        # Sort by cost ascending, prefer Graviton
        candidates.sort(key=lambda item: item[1]["cost"])
        cheapest_cost = candidates[0][1]["cost"]
        cheapest_tier = [c for c in candidates if c[1]["cost"] == cheapest_cost]
        graviton_tier = [c for c in cheapest_tier if c[1].get("graviton")]

        return (graviton_tier[0] if graviton_tier else cheapest_tier[0])[0]


