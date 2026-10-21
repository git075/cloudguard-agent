"""
SQLAlchemy 2.0 ORM Models for Multi-Tenant CloudGuard FinOps.
Defines schemas for customers (tenants), AWS accounts, scan jobs, and pull request audit logs.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


def generate_uuid() -> str:
    """Generates a string UUID v4 for primary keys."""
    return str(uuid.uuid4())


class Customer(Base):
    """
    Tenant Customer Model.
    Each customer represents an organization/company using CloudGuard FinOps.
    Stores customer authentication credentials and cryptographically generated ExternalId.
    """
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Confused Deputy Protection: Per-customer cryptographically secure ExternalId
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    aws_accounts: Mapped[List["AWSAccount"]] = relationship(
        "AWSAccount", back_populates="customer", cascade="all, delete-orphan"
    )
    scan_jobs: Mapped[List["ScanJob"]] = relationship(
        "ScanJob", back_populates="customer", cascade="all, delete-orphan"
    )
    pull_request_logs: Mapped[List["PullRequestLog"]] = relationship(
        "PullRequestLog", back_populates="customer", cascade="all, delete-orphan"
    )


class AWSAccount(Base):
    """
    Customer AWS Account Credentials & Metadata.
    Stores the IAM Role ARN and account ID for cross-account telemetry scanning.
    """
    __tablename__ = "aws_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(String(12), nullable=False)
    role_arn: Mapped[str] = mapped_column(String(255), nullable=False)
    alias: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="aws_accounts")
    scan_jobs: Mapped[List["ScanJob"]] = relationship(
        "ScanJob", back_populates="aws_account", cascade="all, delete-orphan"
    )


class ScanJob(Base):
    """
    Asynchronous Scan Job Execution Record.
    Tracks state of background FinOps optimization scans per AWS account.
    """
    __tablename__ = "scan_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    aws_account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("aws_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending, running, completed, failed
    total_resources_scanned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_savings_identified: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="scan_jobs")
    aws_account: Mapped["AWSAccount"] = relationship("AWSAccount", back_populates="scan_jobs")
    pull_request_logs: Mapped[List["PullRequestLog"]] = relationship(
        "PullRequestLog", back_populates="scan_job", cascade="all, delete-orphan"
    )


class PullRequestLog(Base):
    """
    GitOps PR Audit Log Entry.
    Records every Terraform right-sizing PR created by CloudGuard for a customer resource.
    """
    __tablename__ = "pull_request_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_job_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("scan_jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    original_spec: Mapped[str] = mapped_column(String(100), nullable=False)
    proposed_spec: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_savings_usd: Mapped[float] = mapped_column(Float, nullable=False)
    pr_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="created", nullable=False)  # created, merged, closed, failed
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="pull_request_logs")
    scan_job: Mapped[Optional["ScanJob"]] = relationship("ScanJob", back_populates="pull_request_logs")
