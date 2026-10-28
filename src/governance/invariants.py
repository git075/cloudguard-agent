"""
StateGuard Invariant Engine for Pre-Commit Safety Checks
Directly imports InvariantRegistry and InvariantViolation from PyPI 'stateguard-core' package.
"""
import sys
import site
import logging
from typing import Dict, Any, Callable

# Ensure user site-packages is in python path
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.append(user_site)

logger = logging.getLogger("cloudguard.governance.invariants")

from stateguard import InvariantRegistry, InvariantViolation as InvariantViolationError

__all__ = ["InvariantRegistry", "InvariantViolationError", "get_default_cloudguard_registry"]


def get_default_cloudguard_registry() -> InvariantRegistry:
    """
    Factory creating standard production invariants for CloudGuard using PyPI stateguard-core.
    """
    registry = InvariantRegistry()

    # Rule 1: Peak CPU Headroom (CPU <= 80%)
    @registry.invariant(name="cpu_headroom_check", mode="block", description="Peak CPU <= 80%")
    def cpu_check(s):
        if s.get("status") in ("proposed", "committed") or "status" not in s:
            if s.get("proposed_spec") and s.get("proposed_spec") != s.get("current_spec"):
                return s.get("peak_cpu_percent", 0.0) <= 80.0
        return True

    # Rule 2: Memory Buffer Check (Proposed RAM >= Peak Used RAM * 1.25)
    @registry.invariant(name="ram_safety_buffer_check", mode="block", description="Proposed RAM >= Peak Used RAM * 1.25")
    def ram_check(s):
        if s.get("status") in ("proposed", "committed") or "status" not in s:
            if s.get("proposed_spec") and s.get("proposed_spec") != s.get("current_spec"):
                return s.get("proposed_memory_gb", 0.0) >= (s.get("peak_memory_used_gb", 0.0) * 1.25)
        return True

    # Rule 3: Storage Encryption Requirement (Hardened Fail-Safe Default)
    @registry.invariant(name="storage_encryption_check", mode="block", description="Storage encryption must be enabled")
    def enc_check(s):
        return s.get("storage_encrypted", False) in (True, "true", "True")

    # Rule 4: Private Network Requirement
    @registry.invariant(name="private_network_check", mode="block", description="Public accessibility must be false")
    def net_check(s):
        return s.get("publicly_accessible", False) in (False, "false", "False")

    # Rule 5: Non-Negative Savings Invariant (Prevents spend increases)
    @registry.invariant(name="non_negative_savings_check", mode="block", description="Proposed cost <= original cost and savings >= 0")
    def savings_check(s):
        orig = s.get("original_monthly_cost", 0.0)
        prop = s.get("proposed_monthly_cost", 0.0)
        sav = s.get("monthly_savings_usd", 0.0)
        return prop <= orig and sav >= 0.0

    # Rule 6: Production Database Memory Floor Invariant (RAM >= 4.0 GB)
    @registry.invariant(name="production_min_memory_floor_check", mode="block", description="Proposed RAM >= 4.0 GB for database resources")
    def min_ram_check(s):
        if s.get("resource_type") == "aws_db_instance":
            return s.get("proposed_memory_gb", 0.0) >= 4.0
        return True

    # Rule 7: Extreme Cost Drop Sanity Check (Max 95% single-step reduction)
    @registry.invariant(name="extreme_cost_drop_sanity_check", mode="block", description="Proposed cost >= 5% of original cost")
    def sanity_check(s):
        orig = s.get("original_monthly_cost", 0.0)
        prop = s.get("proposed_monthly_cost", 0.0)
        if orig > 0:
            return prop >= (orig * 0.05)
        return True

    # Rule 8: Valid Workflow Status State Check
    @registry.invariant(name="valid_status_state_check", mode="block", description="Status must be pending, proposed, committed, or rejected")
    def status_check(s):
        return s.get("status", "pending") in ("pending", "proposed", "committed", "rejected")

    # Rule 9: Projected CPU Headroom Check (Projected CPU <= 80% on proposed spec)
    @registry.invariant(name="projected_cpu_headroom_check", mode="block", description="Projected peak CPU <= 80%")
    def proj_cpu_check(s):
        if s.get("status") in ("proposed", "committed"):
            proj_cpu = s.get("projected_cpu_percent", 0.0)
            if proj_cpu > 0.0:
                return proj_cpu <= 80.0
        return True

    # Rule 10: Database Connection Capacity Check (RDS only: connections <= 70% of max limit)
    @registry.invariant(name="db_connections_capacity_check", mode="block", description="Peak DB connections <= 70% of instance limit")
    def conn_capacity_check(s):
        if s.get("resource_type") == "aws_db_instance" and s.get("status") in ("proposed", "committed"):
            peak_conns = s.get("db_connections_max", 0)
            max_limit = s.get("proposed_max_connections", 0)
            if peak_conns > 0 and max_limit > 0:
                return peak_conns <= (max_limit * 0.70)
        return True

    # Rule 11: Valid Catalog Instance Check (Proposed spec must exist in verified pricing catalog)
    @registry.invariant(name="valid_catalog_instance_check", mode="block", description="Proposed spec must exist in verified catalog")
    def catalog_check(s):
        if s.get("status") in ("proposed", "committed"):
            prop_spec = s.get("proposed_spec")
            if not prop_spec:
                return False
            if prop_spec == s.get("current_spec"):
                return True
            from src.agents.finops_agent import INSTANCE_PRICING_CATALOG
            return prop_spec in INSTANCE_PRICING_CATALOG
        return True

    # Rule 12: Engine Architecture Compatibility Check (Oracle / SQL Server cannot use Graviton ARM)
    @registry.invariant(name="engine_architecture_compatibility_check", mode="block", description="Oracle/SQL Server engines cannot run on Graviton ARM")
    def engine_compat_check(s):
        if s.get("resource_type") == "aws_db_instance" and s.get("status") in ("proposed", "committed"):
            engine = str(s.get("engine") or "").lower()
            prop_spec = str(s.get("proposed_spec") or "").lower()
            is_commercial = any(e in engine for e in ("oracle", "sqlserver", "sql-server"))
            is_arm = any(fam in prop_spec for fam in ("r6g", "m6g", "t4g", ".g."))
            if is_commercial and is_arm:
                return False
        return True

    # Rule 13: EC2 Architecture Lock Check (Cannot migrate x86 EC2 to ARM without explicit migration flag)
    @registry.invariant(name="ec2_architecture_lock_check", mode="block", description="x86 EC2 instances cannot migrate to ARM without allow_arm_migration")
    def ec2_arch_check(s):
        if s.get("resource_type") in ("aws_instance", "ec2") and s.get("status") in ("proposed", "committed"):
            curr_spec = str(s.get("current_spec") or "").lower()
            prop_spec = str(s.get("proposed_spec") or "").lower()
            curr_is_x86 = any(fam in curr_spec for fam in ("m5", "r5", "c5", "t3"))
            prop_is_arm = any(fam in prop_spec for fam in ("m6g", "r6g", "c6g", "t4g"))
            allow_arm = s.get("allow_arm_migration", False)
            if curr_is_x86 and prop_is_arm and not allow_arm:
                return False
        return True

    return registry

