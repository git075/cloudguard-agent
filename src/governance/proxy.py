"""
GuardedState Transactional Memory Proxy
Directly imports GuardedState from PyPI 'stateguard-core' package.
"""
import sys
import site
import logging

# Ensure user site-packages is in python path
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.append(user_site)

logger = logging.getLogger("cloudguard.governance.proxy")

from stateguard import GuardedState

__all__ = ["GuardedState"]
