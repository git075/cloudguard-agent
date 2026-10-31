"""
FastAPI AWS Account Management Endpoints.
Allows authenticated tenant customers to connect, list, and manage AWS accounts for scanning.
"""
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_customer
from src.db.session import get_async_db
from src.models.db import AWSAccount, Customer

router = APIRouter(prefix="/api/v1/accounts", tags=["AWS Accounts"])

IAM_ROLE_ARN_REGEX = re.compile(r"^arn:aws[a-zA-Z-]*:iam::(\d{12}):role/[\w+=,.@-]+$")


class ConnectAWSAccountRequest(BaseModel):
    role_arn: str = Field(..., json_schema_extra={"example": "arn:aws:iam::123456789012:role/CloudGuardReadOnlyRole"})
    alias: Optional[str] = Field(None, max_length=100, json_schema_extra={"example": "Production AWS Account"})


class AWSAccountResponse(BaseModel):
    id: str
    account_id: str
    role_arn: str
    alias: Optional[str]
    is_active: bool
    created_at: str


@router.post("/aws", response_model=AWSAccountResponse, status_code=status.HTTP_201_CREATED)
async def connect_aws_account_endpoint(
    req: ConnectAWSAccountRequest,
    current_customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Connects a new AWS Account to the authenticated customer's tenant.
    Validates IAM Role ARN format and extracts the 12-digit AWS Account ID.
    """
    match = IAM_ROLE_ARN_REGEX.match(req.role_arn.strip())
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid IAM Role ARN format. Must follow 'arn:aws:iam::<12-digit-account-id>:role/<role-name>'",
        )

    account_id = match.group(1)

    # Check if account is already connected for this customer
    stmt = select(AWSAccount).where(
        AWSAccount.customer_id == current_customer.id,
        AWSAccount.account_id == account_id,
        AWSAccount.role_arn == req.role_arn.strip(),
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        return AWSAccountResponse(
            id=existing.id,
            account_id=existing.account_id,
            role_arn=existing.role_arn,
            alias=existing.alias,
            is_active=existing.is_active,
            created_at=existing.created_at.isoformat() if existing.created_at else "",
        )

    new_account = AWSAccount(
        customer_id=current_customer.id,
        account_id=account_id,
        role_arn=req.role_arn.strip(),
        alias=req.alias or f"AWS Account ({account_id})",
        is_active=True,
    )
    db.add(new_account)
    await db.commit()
    await db.refresh(new_account)

    return AWSAccountResponse(
        id=new_account.id,
        account_id=new_account.account_id,
        role_arn=new_account.role_arn,
        alias=new_account.alias,
        is_active=new_account.is_active,
        created_at=new_account.created_at.isoformat() if new_account.created_at else "",
    )


@router.get("/aws", response_model=List[AWSAccountResponse])
async def list_customer_aws_accounts_endpoint(
    current_customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Lists all connected AWS accounts for the authenticated customer tenant.
    """
    stmt = select(AWSAccount).where(
        AWSAccount.customer_id == current_customer.id,
        AWSAccount.is_active == True,
    ).order_by(AWSAccount.created_at.desc())
    result = await db.execute(stmt)
    accounts = result.scalars().all()

    return [
        AWSAccountResponse(
            id=acc.id,
            account_id=acc.account_id,
            role_arn=acc.role_arn,
            alias=acc.alias,
            is_active=acc.is_active,
            created_at=acc.created_at.isoformat() if acc.created_at else "",
        )
        for acc in accounts
    ]
