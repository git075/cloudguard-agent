"""
FinOps Cost Optimization Agent — Production Implementation (Phase 1 + Phase 2)
================================================================================
Replaces the POC single if/else with a constraint-based optimal instance selector
that searches across 25+ AWS instance types to find the cheapest tier satisfying
RAM, vCPU, IOPS, and DB connection requirements.

PHASE 1 CHANGES vs POC:
  - INSTANCE_PRICING_CATALOG expanded from 7 → 25+ instance types.
  - Added RDS connection limits per instance type (critical for sizing).
  - Added storage type compatibility flags (gp3 vs io1 IOPS requirements).
  - Pricing sourced from AWS us-east-1 On-Demand rates (update quarterly).

PHASE 2 CHANGES vs POC:
  - propose_optimization() now uses _select_optimal_spec() — a constraint-based
    algorithm that finds the cheapest instance satisfying all requirements.
  - Graviton-upgrade preference: r6g/m6g preferred over r5/m5 for same RAM.
  - DB connection limit enforcement: never propose an instance that maxes out
    connection pool capacity based on historical peak connections.
  - IOPS-aware: if peak IOPS > 3000, skips burstable t4g family.

AWS CONCEPTS:
  - Graviton (g-suffix): ARM-based AWS CPUs offering ~40% better price-performance.
  - gp3 storage: General Purpose SSD baseline 3000 IOPS free; extra IOPS provisioned.
  - io1 storage: Provisioned IOPS SSD — required for > 64000 IOPS workloads.
  - RDS max_connections: Hard limit per instance type. Exceeding causes 'too many
    connections' errors that crash applications. Formula: roughly 10 per GB RAM.
"""
import logging
from typing import Dict, Any, List, Optional, Tuple

from src.models.telemetry import ResourceTelemetry
from src.models.swarm import FinOpsProposal

logger = logging.getLogger("cloudguard.finops_agent")


# ─────────────────────────────────────────────────────────────────────────────
# Production Instance Pricing Catalog
# Source: AWS us-east-1 On-Demand pricing (RDS PostgreSQL Single-AZ, Linux EC2)
# Update this quarterly or integrate with the AWS Pricing API (Phase 1.4).
#
# Fields:
#   cost:         USD/month On-Demand (730 hours/mo)
#   ram_gb:       Total RAM in GB
#   vcpu:         Number of vCPUs
#   family:       Instance family (r5, r6g, m6g, t4g, etc.)
#   graviton:     True if ARM Graviton processor (requires arm64-compatible AMI/engine)
#   max_conn_rds: Approximate RDS max_connections limit (formula: DBInstanceClassMemory/12582880)
#   min_iops:     0 for burstable; baseline IOPS for gp3 storage
#   resource_type: 'rds' or 'ec2'
# ─────────────────────────────────────────────────────────────────────────────
INSTANCE_PRICING_CATALOG: Dict[str, Dict[str, Any]] = {

    # ── RDS Memory-Optimized (Intel x86 r5) ──────────────────────────────────
    "db.r5.large":    {"cost": 187.00,  "ram_gb": 16.0,  "vcpu": 2, "family": "r5",  "graviton": False, "max_conn_rds": 1320,  "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "rds"},
    "db.r5.xlarge":   {"cost": 374.00,  "ram_gb": 32.0,  "vcpu": 4, "family": "r5",  "graviton": False, "max_conn_rds": 2630,  "ebs_mbps": 2500, "net_mbps": 5000,  "resource_type": "rds"},
    "db.r5.2xlarge":  {"cost": 749.00,  "ram_gb": 64.0,  "vcpu": 8, "family": "r5",  "graviton": False, "max_conn_rds": 5310,  "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "rds"},
    "db.r5.4xlarge":  {"cost": 1498.00, "ram_gb": 128.0, "vcpu": 16,"family": "r5",  "graviton": False, "max_conn_rds": 10630, "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "rds"},

    # ── RDS Memory-Optimized (ARM Graviton r6g) — Preferred for cost savings ──
    "db.r6g.large":   {"cost": 148.00,  "ram_gb": 16.0,  "vcpu": 2, "family": "r6g", "graviton": True,  "max_conn_rds": 1320,  "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "rds"},
    "db.r6g.xlarge":  {"cost": 296.00,  "ram_gb": 32.0,  "vcpu": 4, "family": "r6g", "graviton": True,  "max_conn_rds": 2630,  "ebs_mbps": 2500, "net_mbps": 5000,  "resource_type": "rds"},
    "db.r6g.2xlarge": {"cost": 592.00,  "ram_gb": 64.0,  "vcpu": 8, "family": "r6g", "graviton": True,  "max_conn_rds": 5310,  "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "rds"},
    "db.r6g.4xlarge": {"cost": 1185.00, "ram_gb": 128.0, "vcpu": 16,"family": "r6g", "graviton": True,  "max_conn_rds": 10630, "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "rds"},

    # ── RDS General Purpose (ARM Graviton m6g) ───────────────────────────────
    "db.m6g.large":   {"cost": 108.00,  "ram_gb": 8.0,   "vcpu": 2, "family": "m6g", "graviton": True,  "max_conn_rds": 660,   "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "rds"},
    "db.m6g.xlarge":  {"cost": 216.00,  "ram_gb": 16.0,  "vcpu": 4, "family": "m6g", "graviton": True,  "max_conn_rds": 1320,  "ebs_mbps": 2500, "net_mbps": 5000,  "resource_type": "rds"},
    "db.m6g.2xlarge": {"cost": 432.00,  "ram_gb": 32.0,  "vcpu": 8, "family": "m6g", "graviton": True,  "max_conn_rds": 2630,  "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "rds"},

    # ── RDS Burstable (ARM Graviton t4g) — Cheapest, but CPU credit limited ──
    "db.t4g.micro":   {"cost": 14.00,   "ram_gb": 1.0,   "vcpu": 2, "family": "t4g", "graviton": True,  "max_conn_rds": 68,    "ebs_mbps": 200,  "net_mbps": 1000,  "resource_type": "rds"},
    "db.t4g.small":   {"cost": 28.00,   "ram_gb": 2.0,   "vcpu": 2, "family": "t4g", "graviton": True,  "max_conn_rds": 136,   "ebs_mbps": 400,  "net_mbps": 1500,  "resource_type": "rds"},
    "db.t4g.medium":  {"cost": 56.00,   "ram_gb": 4.0,   "vcpu": 2, "family": "t4g", "graviton": True,  "max_conn_rds": 310,   "ebs_mbps": 800,  "net_mbps": 2000,  "resource_type": "rds"},
    "db.t4g.large":   {"cost": 112.00,  "ram_gb": 8.0,   "vcpu": 2, "family": "t4g", "graviton": True,  "max_conn_rds": 660,   "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "rds"},

    # ── EC2 General Purpose (Intel x86 m5) ───────────────────────────────────
    "m5.large":       {"cost": 70.00,   "ram_gb": 8.0,   "vcpu": 2, "family": "m5",  "graviton": False, "max_conn_rds": 0,     "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "ec2"},
    "m5.xlarge":      {"cost": 140.00,  "ram_gb": 16.0,  "vcpu": 4, "family": "m5",  "graviton": False, "max_conn_rds": 0,     "ebs_mbps": 2500, "net_mbps": 5000,  "resource_type": "ec2"},
    "m5.2xlarge":     {"cost": 280.00,  "ram_gb": 32.0,  "vcpu": 8, "family": "m5",  "graviton": False, "max_conn_rds": 0,     "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "ec2"},

    # ── EC2 General Purpose (ARM Graviton m6g) — Preferred ───────────────────
    "m6g.medium":     {"cost": 28.00,   "ram_gb": 4.0,   "vcpu": 1, "family": "m6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 600,  "net_mbps": 1500,  "resource_type": "ec2"},
    "m6g.large":      {"cost": 56.00,   "ram_gb": 8.0,   "vcpu": 2, "family": "m6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "ec2"},
    "m6g.xlarge":     {"cost": 112.00,  "ram_gb": 16.0,  "vcpu": 4, "family": "m6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 2500, "net_mbps": 5000,  "resource_type": "ec2"},
    "m6g.2xlarge":    {"cost": 224.00,  "ram_gb": 32.0,  "vcpu": 8, "family": "m6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "ec2"},

    # ── EC2 Burstable (ARM Graviton t4g) ─────────────────────────────────────
    "t4g.small":      {"cost": 12.00,   "ram_gb": 2.0,   "vcpu": 2, "family": "t4g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 400,  "net_mbps": 1500,  "resource_type": "ec2"},
    "t4g.medium":     {"cost": 24.00,   "ram_gb": 4.0,   "vcpu": 2, "family": "t4g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 800,  "net_mbps": 2000,  "resource_type": "ec2"},
    "t4g.large":      {"cost": 48.00,   "ram_gb": 8.0,   "vcpu": 2, "family": "t4g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "ec2"},

    # ── EC2 Compute-Optimized (Intel x86 c5) ─────────────────────────────────
    "c5.large":       {"cost": 62.00,   "ram_gb": 4.0,   "vcpu": 2, "family": "c5",  "graviton": False, "max_conn_rds": 0,     "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "ec2"},
    "c5.xlarge":      {"cost": 124.00,  "ram_gb": 8.0,   "vcpu": 4, "family": "c5",  "graviton": False, "max_conn_rds": 0,     "ebs_mbps": 2500, "net_mbps": 5000,  "resource_type": "ec2"},
    "c5.2xlarge":     {"cost": 248.00,  "ram_gb": 16.0,  "vcpu": 8, "family": "c5",  "graviton": False, "max_conn_rds": 0,     "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "ec2"},

    # ── EC2 Compute-Optimized (ARM Graviton c6g) ─────────────────────────────
    "c6g.medium":     {"cost": 25.00,   "ram_gb": 2.0,   "vcpu": 1, "family": "c6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 600,  "net_mbps": 1500,  "resource_type": "ec2"},
    "c6g.large":      {"cost": 50.00,   "ram_gb": 4.0,   "vcpu": 2, "family": "c6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "ec2"},
    "c6g.xlarge":     {"cost": 100.00,  "ram_gb": 8.0,   "vcpu": 4, "family": "c6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 2500, "net_mbps": 5000,  "resource_type": "ec2"},
    "c6g.2xlarge":    {"cost": 200.00,  "ram_gb": 16.0,  "vcpu": 8, "family": "c6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "ec2"},

    # ── EC2 Memory-Optimized (Intel x86 r5) ──────────────────────────────────
    "r5.large":       {"cost": 92.00,   "ram_gb": 16.0,  "vcpu": 2, "family": "r5",  "graviton": False, "max_conn_rds": 0,     "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "ec2"},
    "r5.xlarge":      {"cost": 184.00,  "ram_gb": 32.0,  "vcpu": 4, "family": "r5",  "graviton": False, "max_conn_rds": 0,     "ebs_mbps": 2500, "net_mbps": 5000,  "resource_type": "ec2"},
    "r5.2xlarge":     {"cost": 368.00,  "ram_gb": 64.0,  "vcpu": 8, "family": "r5",  "graviton": False, "max_conn_rds": 0,     "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "ec2"},

    # ── EC2 Memory-Optimized (ARM Graviton r6g) ──────────────────────────────
    "r6g.large":      {"cost": 74.00,   "ram_gb": 16.0,  "vcpu": 2, "family": "r6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 1250, "net_mbps": 2500,  "resource_type": "ec2"},
    "r6g.xlarge":     {"cost": 148.00,  "ram_gb": 32.0,  "vcpu": 4, "family": "r6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 2500, "net_mbps": 5000,  "resource_type": "ec2"},
    "r6g.2xlarge":    {"cost": 296.00,  "ram_gb": 64.0,  "vcpu": 8, "family": "r6g", "graviton": True,  "max_conn_rds": 0,     "ebs_mbps": 4750, "net_mbps": 10000, "resource_type": "ec2"},
}


def calculate_projected_cpu(current_spec: str, proposed_spec: str, peak_cpu_percent: float) -> float:
    """
    Calculates projected peak CPU utilization on a proposed target instance.
    Accounts for differing vCPU core counts and architectural IPC differences:
    ARM Graviton3 (r6g/m6g/c6g) delivers ~20% higher performance per vCPU vs Intel x86 (r5/m5/c5).
    """
    curr_info = INSTANCE_PRICING_CATALOG.get(current_spec, {})
    prop_info = INSTANCE_PRICING_CATALOG.get(proposed_spec, {})

    curr_vcpu = curr_info.get("vcpu")
    if not curr_vcpu:
        spec_lower = current_spec.lower()
        if "8xlarge" in spec_lower:
            curr_vcpu = 32
        elif "4xlarge" in spec_lower:
            curr_vcpu = 16
        elif "2xlarge" in spec_lower:
            curr_vcpu = 8
        elif "xlarge" in spec_lower:
            curr_vcpu = 4
        elif "large" in spec_lower:
            curr_vcpu = 2
        elif "medium" in spec_lower:
            curr_vcpu = 1
        else:
            curr_vcpu = 4

    prop_vcpu = prop_info.get("vcpu", 2)
    if prop_vcpu <= 0:
        prop_vcpu = 2

    # IPC factor: Graviton ARM vs Intel x86
    is_curr_arm = curr_info.get("graviton", False) or any(g in current_spec.lower() for g in ("r6g", "m6g", "c6g", "t4g", ".g."))
    is_prop_arm = prop_info.get("graviton", False) or any(g in proposed_spec.lower() for g in ("r6g", "m6g", "c6g", "t4g", ".g."))

    if not is_curr_arm and is_prop_arm:
        ipc_factor = 1.20  # Graviton upgrade yields 20% IPC boost
    elif is_curr_arm and not is_prop_arm:
        ipc_factor = 0.83  # Downgrading from ARM to Intel loses 17% IPC
    else:
        ipc_factor = 1.00

    active_cores = curr_vcpu * (peak_cpu_percent / 100.0)
    projected_cpu = (active_cores / (prop_vcpu * ipc_factor)) * 100.0
    return projected_cpu


# Safety headroom factor for DB connections: never use more than 70% of max_conn limit
DB_CONNECTION_SAFETY_FACTOR = 0.70

# Burstable CPU threshold: t4g families should not be proposed if avg CPU > this
BURSTABLE_CPU_AVG_THRESHOLD = 20.0

# IOPS threshold above which burstable family is excluded
BURSTABLE_IOPS_THRESHOLD = 3000.0


class FinOpsAgent:
    """
    Agent responsible for analyzing cloud spend and generating optimal cost-reduction proposals.

    Phase 2 upgrade: Uses constraint-based _select_optimal_spec() instead of
    hardcoded if/else. Finds the globally cheapest instance type satisfying all
    operational requirements from the full 25+ instance catalog.
    """

    def propose_optimization(self, telemetry: ResourceTelemetry) -> FinOpsProposal:
        """
        Generates the lowest-cost safe proposal for a resource.

        Decision logic (in order):
          1. Determine catalog resource type ('rds' or 'ec2').
          2. Calculate required RAM with 1.25x safety buffer.
          3. Apply workload constraints (burstable exclusion, connection limits).
          4. Find cheapest catalog entry satisfying all constraints.
          5. Build FinOpsProposal with computed savings.
        """
        logger.info(
            "FinOps Agent analyzing resource: %s (%s) @ $%.2f/mo",
            telemetry.resource_id, telemetry.current_instance_type, telemetry.monthly_cost_usd
        )

        catalog_type = "rds" if telemetry.resource_type == "aws_db_instance" else "ec2"

        # Check engine compatibility (Oracle / SQL Server cannot run on ARM Graviton)
        engine_str = str(getattr(telemetry, "engine", None) or telemetry.tags.get("engine", "")).lower()
        is_commercial_engine = any(e in engine_str for e in ("oracle", "sqlserver", "sql-server"))

        # Check Multi-AZ deployment (Multi-AZ doubles monthly instance cost)
        is_multi_az = getattr(telemetry, "multi_az", False) or (str(telemetry.tags.get("multi_az", "")).lower() in ("true", "1"))
        cost_multiplier = 2.0 if is_multi_az else 1.0

        # Check EC2 Architecture Lock (x86 EC2 instances cannot boot on ARM without AMI migration)
        allow_arm_migration = str(telemetry.tags.get("allow_arm_migration", "")).lower() in ("true", "1")
        curr_is_x86_ec2 = (catalog_type == "ec2" and any(fam in telemetry.current_instance_type for fam in ("m5", "r5", "c5", "t3")))
        exclude_arm = is_commercial_engine or (curr_is_x86_ec2 and not allow_arm_migration)

        # The arch agent will apply 1.25x buffer, but FinOps proposes aggressively
        # using 1.10x (10% buffer) to give arch agent room to counter-propose upward.
        required_ram_gb = max(1.0, telemetry.peak_memory_used_gb * 1.10)

        # Build constraint flags for the selector
        constraints = {
            "exclude_burstable": self._should_exclude_burstable(telemetry),
            "exclude_arm": exclude_arm,
            "cost_multiplier": cost_multiplier,
            "min_db_connections": telemetry.db_connections_max if catalog_type == "rds" else 0,
            "high_iops": telemetry.is_io_intensive,
            "peak_cpu_percent": telemetry.cpu_max_percent,
            "max_safe_cpu": 80.0,
            "network_mbps_required": max(telemetry.network_in_mb_max, telemetry.network_out_mb_max) * 8.0,
            "ebs_mbps_required": ((telemetry.io_read_iops_max + telemetry.io_write_iops_max) * 16.0) / 1024.0,
            "max_cost_limit": telemetry.monthly_cost_usd,
        }

        target_spec, spec_info = self._select_optimal_spec(
            catalog_type=catalog_type,
            required_ram_gb=required_ram_gb,
            constraints=constraints,
            current_spec=telemetry.current_instance_type,
        )

        proposed_cost = float(spec_info["cost"]) * cost_multiplier
        savings = float(max(0.0, telemetry.monthly_cost_usd - proposed_cost))

        # Build rationale string
        rationale_parts = [
            f"Migrate {telemetry.current_instance_type} → {target_spec}",
            f"(${telemetry.monthly_cost_usd:.0f}/mo → ${proposed_cost:.0f}/mo, saving ${savings:.0f}/mo).",
        ]
        if spec_info.get("graviton"):
            rationale_parts.append("Graviton ARM processor: ~40% better price-performance.")
        elif exclude_arm:
            if is_commercial_engine:
                rationale_parts.append(f"Graviton excluded: Engine '{engine_str}' requires x86_64 architecture.")
            elif curr_is_x86_ec2:
                rationale_parts.append("Graviton excluded: x86_64 AMI lock (requires allow_arm_migration tag).")
        if is_multi_az:
            rationale_parts.append("Multi-AZ pricing applied (2x Single-AZ baseline).")
        if constraints["exclude_burstable"] and "t4g" not in target_spec:
            rationale_parts.append(f"Burstable family excluded: avg CPU {telemetry.cpu_avg_percent:.1f}% > {BURSTABLE_CPU_AVG_THRESHOLD}% threshold.")
        if constraints["min_db_connections"] > 0:
            safe_conn_limit = int(spec_info.get("max_conn_rds", 0) * DB_CONNECTION_SAFETY_FACTOR)
            rationale_parts.append(
                f"Peak connections ({telemetry.db_connections_max}) within safe limit of {safe_conn_limit} "
                f"({int(DB_CONNECTION_SAFETY_FACTOR * 100)}% of {spec_info.get('max_conn_rds', 0)} max)."
            )
        if constraints.get("peak_cpu_percent", 0) > 0 and target_spec != telemetry.current_instance_type:
            proj_cpu = calculate_projected_cpu(telemetry.current_instance_type, target_spec, constraints["peak_cpu_percent"])
            rationale_parts.append(f"Projected peak CPU utilization: {proj_cpu:.1f}% (safe ceiling <= 80%).")

        return FinOpsProposal(
            resource_id=telemetry.resource_id,
            current_spec=telemetry.current_instance_type,
            proposed_spec=target_spec,
            current_monthly_cost=telemetry.monthly_cost_usd,
            proposed_monthly_cost=proposed_cost,
            estimated_savings_usd=savings,
            proposed_ram_gb=float(spec_info["ram_gb"]),
            proposed_vcpu=int(spec_info["vcpu"]),
            rationale=" ".join(rationale_parts),
        )

    def _select_optimal_spec(
        self,
        catalog_type: str,
        required_ram_gb: float,
        constraints: Dict[str, Any],
        current_spec: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Core constraint-based optimal instance selector.

        Algorithm:
          1. Filter catalog to only matching resource type (rds/ec2).
          2. Filter out instances with insufficient RAM.
          3. Filter out instances where projected CPU would exceed max safe threshold (Core Collapse Prevention).
          4. Filter out ARM Graviton if engine or AMI architecture is incompatible.
          5. Filter out burstable (t4g) if workload is sustained (high avg CPU or IOPS).
          6. Filter out instances with insufficient DB connection limits.
          7. Filter out instances with insufficient Network / EBS bandwidth.
          8. Filter out current spec and more expensive instances.
          9. Sort remaining candidates by cost ascending; prefer Graviton on cost ties.
          10. Return cheapest valid candidate; fall back to current spec on no match.
        """
        # Step 1: Filter by resource type
        candidates = [
            (spec, info) for spec, info in INSTANCE_PRICING_CATALOG.items()
            if info["resource_type"] == catalog_type
        ]

        # Step 2: Filter by minimum RAM requirement
        candidates = [(s, i) for s, i in candidates if i["ram_gb"] >= required_ram_gb]

        # Step 3: Enforce Projected vCPU Utilization ceiling (Core Collapse Prevention)
        peak_cpu = constraints.get("peak_cpu_percent", 0.0)
        max_safe_cpu = constraints.get("max_safe_cpu", 80.0)
        if peak_cpu > 0:
            candidates = [
                (s, i) for s, i in candidates
                if calculate_projected_cpu(current_spec, s, peak_cpu) <= max_safe_cpu
            ]

        # Step 4: Exclude ARM Graviton if engine or AMI is incompatible
        if constraints.get("exclude_arm"):
            candidates = [(s, i) for s, i in candidates if not i.get("graviton", False)]

        # Step 5: Exclude burstable (t4g) if workload is sustained
        if constraints.get("exclude_burstable"):
            candidates = [(s, i) for s, i in candidates if i["family"] != "t4g"]

        # Step 6: Enforce DB connection safety limit (RDS only)
        min_db_conn = constraints.get("min_db_connections", 0)
        if min_db_conn > 0 and catalog_type == "rds":
            required_conn_capacity = int(min_db_conn / DB_CONNECTION_SAFETY_FACTOR)
            candidates = [
                (s, i) for s, i in candidates
                if i.get("max_conn_rds", 0) >= required_conn_capacity
            ]

        # Step 7: Enforce Network Bandwidth limit
        net_required = constraints.get("network_mbps_required", 0.0)
        if net_required > 0:
            candidates = [
                (s, i) for s, i in candidates
                if i.get("net_mbps", 1000) >= (net_required * 1.20)
            ]

        # Step 8: Enforce EBS / Storage IOPS Bandwidth limit
        ebs_required = constraints.get("ebs_mbps_required", 0.0)
        if ebs_required > 0:
            candidates = [
                (s, i) for s, i in candidates
                if i.get("ebs_mbps", 500) >= (ebs_required * 1.20)
            ]

        # Step 9: Remove current spec (we must propose a different instance)
        candidates = [(s, i) for s, i in candidates if s != current_spec]

        # Step 10: Strictly filter for cost reduction (cannot propose more expensive spec)
        max_cost = constraints.get("max_cost_limit", 0.0)
        cost_mult = constraints.get("cost_multiplier", 1.0)
        if max_cost > 0:
            candidates = [(s, i) for s, i in candidates if (i["cost"] * cost_mult) < max_cost]



        if not candidates:
            logger.warning(
                "No cheaper candidates found for current_spec='%s' with required_ram_gb=%.1f. "
                "Keeping current spec (already optimal or over-constrained).",
                current_spec, required_ram_gb
            )
            # Fall back to current spec info from catalog or safe default
            fallback_info = INSTANCE_PRICING_CATALOG.get(
                current_spec,
                {"cost": 0.0, "ram_gb": required_ram_gb, "vcpu": 2, "family": "r5", "graviton": False, "resource_type": catalog_type}
            )
            return current_spec, fallback_info

        # Step 6: Sort by cost ascending
        candidates.sort(key=lambda item: item[1]["cost"])

        # Step 7: Among the cheapest tier, prefer Graviton
        cheapest_cost = candidates[0][1]["cost"]
        cheapest_tier = [(s, i) for s, i in candidates if i["cost"] == cheapest_cost]
        graviton_in_tier = [(s, i) for s, i in cheapest_tier if i.get("graviton")]

        if graviton_in_tier:
            best = graviton_in_tier[0]
        else:
            best = cheapest_tier[0]

        logger.info(
            "FinOps optimal spec selected: %s ($%.2f/mo, %.0f GB RAM, graviton=%s)",
            best[0], best[1]["cost"], best[1]["ram_gb"], best[1].get("graviton", False)
        )
        return best

    def _should_exclude_burstable(self, telemetry: ResourceTelemetry) -> bool:
        """
        Determines whether burstable (t4g) family instances should be excluded.

        Burstable instances use CPU credit pools. If average CPU utilization
        exceeds ~20%, the instance drains credits and throttles to a baseline
        CPU level — causing severe application performance degradation.

        Exclusion conditions:
          - Average CPU > BURSTABLE_CPU_AVG_THRESHOLD (20%)
          - Peak IOPS > BURSTABLE_IOPS_THRESHOLD (3000 combined)
        """
        if telemetry.cpu_avg_percent > BURSTABLE_CPU_AVG_THRESHOLD:
            logger.info(
                "Excluding burstable family: avg CPU %.1f%% > threshold %.1f%%",
                telemetry.cpu_avg_percent, BURSTABLE_CPU_AVG_THRESHOLD
            )
            return True

        if telemetry.is_io_intensive:
            logger.info(
                "Excluding burstable family: peak IOPS %.0f > threshold %.0f",
                telemetry.peak_iops, BURSTABLE_IOPS_THRESHOLD
            )
            return True

        return False
