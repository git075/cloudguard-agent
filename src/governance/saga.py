"""
StateGuard Distributed Saga & Compensation Coordinator
Directly imports Saga, SagaCoordinator, and CompensatingAction from PyPI 'stateguard-core' package.
"""
import sys
import site
import logging

# Ensure user site-packages is in python path
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.append(user_site)

logger = logging.getLogger("cloudguard.governance.saga")

from stateguard import Saga, SagaCoordinator, CompensatingAction

__all__ = ["Saga", "SagaCoordinator", "CompensatingAction"]
