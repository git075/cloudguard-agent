"""
StateGuard Statistical Drift Detector
Directly imports DriftDetector and DriftViolation from PyPI 'stateguard-core' package.
"""
import sys
import site
import logging

# Ensure user site-packages is in python path
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.append(user_site)

logger = logging.getLogger("cloudguard.governance.drift")

from stateguard import DriftDetector, DriftViolation as DriftAnomalyViolation

__all__ = ["DriftDetector", "DriftAnomalyViolation"]
