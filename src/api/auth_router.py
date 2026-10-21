"""
FastAPI Authentication & Registration Endpoints.
Allows customer onboarding, JWT login, and external_id retrieval.
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_customer
from src.db.session import get_async_db
from src.models.db import Customer
from src.services.auth import (
    authenticate_customer_async,
    create_access_token,
    register_customer_async,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# Pydantic Schemas
class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, json_schema_extra={"example": "Acme Corp"})
    email: EmailStr = Field(..., json_schema_extra={"example": "devops@acme.com"})
    password: str = Field(..., min_length=8, json_schema_extra={"example": "SecurePassword123!"})


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., json_schema_extra={"example": "devops@acme.com"})
    password: str = Field(..., json_schema_extra={"example": "SecurePassword123!"})



class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer_id: str
    email: str
    external_id: str


class CustomerResponse(BaseModel):
    id: str
    name: str
    email: str
    external_id: str
    is_active: bool


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_customer_endpoint(
    req: RegisterRequest, db: AsyncSession = Depends(get_async_db)
):
    """
    Registers a new tenant organization in CloudGuard FinOps.
    Generates a unique ExternalId for AWS IAM AssumeRole security.
    """
    try:
        customer = await register_customer_async(
            db=db, name=req.name, email=req.email, password=req.password
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )

    token = create_access_token(customer_id=customer.id, email=customer.email)
    return TokenResponse(
        access_token=token,
        customer_id=customer.id,
        email=customer.email,
        external_id=customer.external_id,
    )


@router.post("/login", response_model=TokenResponse)
async def login_customer_endpoint(
    req: LoginRequest, db: AsyncSession = Depends(get_async_db)
):
    """
    Authenticates a tenant customer and returns a signed JWT bearer token.
    """
    customer = await authenticate_customer_async(
        db=db, email=req.email, password=req.password
    )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(customer_id=customer.id, email=customer.email)
    return TokenResponse(
        access_token=token,
        customer_id=customer.id,
        email=customer.email,
        external_id=customer.external_id,
    )


@router.get("/me", response_model=CustomerResponse)
async def get_current_customer_profile(
    current_customer: Customer = Depends(get_current_customer),
):
    """
    Returns the authenticated customer's profile including their unique ExternalId.
    """
    return CustomerResponse(
        id=current_customer.id,
        name=current_customer.name,
        email=current_customer.email,
        external_id=current_customer.external_id,
        is_active=current_customer.is_active,
    )
