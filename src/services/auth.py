"""
Authentication & Multi-Tenant Security Service for CloudGuard FinOps.
Provides JWT token creation/validation, bcrypt password hashing,
and cryptographically secure per-tenant ExternalId generation.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.models.db import Customer

import bcrypt

# JWT Configuration
INSECURE_DEFAULT_JWT_KEY = "cloudguard-finops-production-super-secret-jwt-key-2026"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", INSECURE_DEFAULT_JWT_KEY)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

def verify_production_jwt_secret() -> None:
    """
    Enforces that a cryptographically secure JWT_SECRET_KEY is configured in production.
    Raises RuntimeError if the environment is production and the secret is missing or default.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    secret = os.getenv("JWT_SECRET_KEY")
    if env in ("production", "prod") and (not secret or secret == INSECURE_DEFAULT_JWT_KEY):
        raise RuntimeError(
            "FATAL SECURITY VIOLATION: JWT_SECRET_KEY environment variable must be set to a "
            "cryptographically secure secret in production environments! Refusing to start."
        )

# Enforce secure secret in production environments at import time
verify_production_jwt_secret()



def hash_password(password: str) -> str:
    """Hashes a plain text password using bcrypt."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against its bcrypt hash."""
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hash_bytes)



def generate_external_id() -> str:
    """
    Generates a cryptographically secure, unique ExternalId per customer tenant.
    Format: 'cg_ext_' + 56 random hex characters (64 chars total).
    Used in IAM AssumeRole to prevent AWS Confused Deputy attacks.
    """
    return f"cg_ext_{secrets.token_hex(28)}"


def create_access_token(customer_id: str, email: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    Generates a signed JWT Access Token containing customer tenant claims.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": customer_id,
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "iss": "cloudguard-finops",
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT access token.
    Raises jwt.PyJWTError if token is expired, tampered with, or invalid.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], issuer="cloudguard-finops")
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token signature has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid authentication token: {str(e)}")


async def register_customer_async(
    db: AsyncSession, name: str, email: str, password: str
) -> Customer:
    """
    Registers a new tenant customer with hashed password and auto-generated ExternalId.
    """
    # Check if email already exists
    stmt = select(Customer).where(Customer.email == email)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError(f"Customer with email '{email}' already exists.")

    password_h = hash_password(password)
    ext_id = generate_external_id()

    new_customer = Customer(
        name=name,
        email=email,
        password_hash=password_h,
        external_id=ext_id,
        is_active=True,
    )

    db.add(new_customer)
    await db.commit()
    await db.refresh(new_customer)
    return new_customer


def register_customer_sync(
    db: Session, name: str, email: str, password: str
) -> Customer:
    """Synchronous customer registration helper."""
    existing = db.query(Customer).filter(Customer.email == email).first()
    if existing:
        raise ValueError(f"Customer with email '{email}' already exists.")

    new_customer = Customer(
        name=name,
        email=email,
        password_hash=hash_password(password),
        external_id=generate_external_id(),
        is_active=True,
    )
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return new_customer


async def authenticate_customer_async(
    db: AsyncSession, email: str, password: str
) -> Optional[Customer]:
    """
    Authenticates customer by email and password.
    Returns Customer object if valid, None if invalid.
    """
    stmt = select(Customer).where(Customer.email == email)
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()
    if not customer:
        return None

    if not verify_password(password, customer.password_hash):
        return None

    return customer
