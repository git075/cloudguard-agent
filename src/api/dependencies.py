"""
FastAPI Authentication & Multi-Tenant Dependencies.
Provides Bearer JWT verification and current tenant customer resolution.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_db
from src.models.db import Customer
from src.services.auth import decode_access_token

security = HTTPBearer()


async def get_current_customer(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> Customer:
    """
    FastAPI dependency to extract JWT Bearer token, validate claims,
    and resolve active customer tenant from database.
    """
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        customer_id: str = payload.get("sub", "")
        if not customer_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing subject (sub)",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(Customer).where(Customer.id == customer_id)
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer tenant not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer tenant account is inactive",
        )

    return customer


security_optional = HTTPBearer(auto_error=False)


async def get_optional_customer(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_optional)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> Customer:
    """
    Optional customer resolution. Returns Customer if valid Bearer token provided, None otherwise.
    """
    if not credentials or not credentials.credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        customer_id: str = payload.get("sub", "")
        if not customer_id:
            return None
        stmt = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(stmt)
        customer = result.scalar_one_or_none()
        return customer if (customer and customer.is_active) else None
    except Exception:
        return None

