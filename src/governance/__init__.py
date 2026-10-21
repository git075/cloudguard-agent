"""
CloudGuard Governance & StateGuard Integration Package
Exports engine, proxy, invariants, drift, and saga primitives.
"""
import sys
import site

user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.append(user_site)

from src.governance.proxy import GuardedState
from src.governance.invariants import get_default_cloudguard_registry, InvariantRegistry, InvariantViolationError
from src.governance.drift import DriftDetector, DriftAnomalyViolation
from src.governance.saga import Saga, SagaCoordinator, CompensatingAction
from src.governance.engine import CloudGuardGovernanceEngine

__all__ = [
    "GuardedState",
    "get_default_cloudguard_registry",
    "InvariantRegistry",
    "InvariantViolationError",
    "DriftDetector",
    "DriftAnomalyViolation",
    "Saga",
    "SagaCoordinator",
    "CompensatingAction",
    "CloudGuardGovernanceEngine",
]
