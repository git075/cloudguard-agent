"""
API Package for CloudGuard FinOps.
Exports FastAPI routers and authentication dependencies.
"""
from src.api.auth_router import router as auth_router
from src.api.scan_router import router as scan_router
from src.api.dependencies import get_current_customer

__all__ = ["auth_router", "scan_router", "get_current_customer"]

