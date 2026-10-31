"""
Unit & Integration Tests for Authentication, JWT Tokens, ExternalId, and FastAPI Auth Routes.
"""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.models.db import Base, Customer
from src.db.session import get_async_db
from src.api.auth_router import router as auth_router
from src.api.account_router import router as account_router
from src.services.auth import (
    create_access_token,
    decode_access_token,
    generate_external_id,
    hash_password,
    verify_password,
)

# Set up test FastAPI app
app = FastAPI()
app.include_router(auth_router)
app.include_router(account_router)


@pytest.fixture
def test_engine_session():
    """Creates in-memory database engine for FastAPI test client."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    return engine


@pytest_asyncio.fixture
async def async_test_session(test_engine_session):
    async with test_engine_session.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(test_engine_session, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await test_engine_session.dispose()


def test_password_hashing_and_verification():
    """Test bcrypt hashing and matching verification."""
    password = "MySecurePassword2026!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_external_id_generation_and_uniqueness():
    """Test ExternalId format and randomness uniqueness."""
    ext1 = generate_external_id()
    ext2 = generate_external_id()

    assert ext1.startswith("cg_ext_")
    assert ext2.startswith("cg_ext_")
    assert ext1 != ext2
    assert len(ext1) >= 60


def test_jwt_token_lifecycle():
    """Test creation and decoding of valid JWT access tokens."""
    cust_id = "cust-uuid-12345"
    email = "admin@acme.com"

    token = create_access_token(customer_id=cust_id, email=email)
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload["sub"] == cust_id
    assert payload["email"] == email
    assert payload["iss"] == "cloudguard-finops"


def test_invalid_jwt_token():
    """Test that tampered/invalid JWT tokens raise ValueError."""
    with pytest.raises(ValueError, match="Invalid authentication token"):
        decode_access_token("invalid.jwt.token")


@pytest.mark.asyncio
async def test_fastapi_auth_register_login_flow(async_test_session: AsyncSession):
    """Test complete FastAPI customer registration, login, and /me endpoints."""
    
    # Override get_async_db dependency to use in-memory sqlite session
    async def override_get_db():
        yield async_test_session

    app.dependency_overrides[get_async_db] = override_get_db
    client = TestClient(app)

    # 1. Register new tenant customer
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Oscorp",
            "email": "norman@oscorp.com",
            "password": "GoblinPassword123!",
        },
    )
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert "access_token" in reg_data
    assert reg_data["email"] == "norman@oscorp.com"
    assert reg_data["external_id"].startswith("cg_ext_")

    token = reg_data["access_token"]
    cust_id = reg_data["customer_id"]

    # 2. Login with registered customer
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "norman@oscorp.com", "password": "GoblinPassword123!"},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["customer_id"] == cust_id

    # 3. Access protected GET /api/v1/auth/me endpoint using Bearer Token
    headers = {"Authorization": f"Bearer {token}"}
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["name"] == "Oscorp"
    assert me_data["email"] == "norman@oscorp.com"
    assert me_data["external_id"] == reg_data["external_id"]

    # 4. Access /me with invalid token should fail 401
    bad_res = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad_token"})
    assert bad_res.status_code == 401

    # Clear dependency overrides
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_fastapi_aws_account_connect_and_list(async_test_session: AsyncSession):
    """Test connecting AWS accounts, validating IAM Role ARNs, and listing tenant accounts."""
    async def override_get_db():
        yield async_test_session

    app.dependency_overrides[get_async_db] = override_get_db
    client = TestClient(app)

    # Register customer
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Stark Industries",
            "email": "tony@stark.com",
            "password": "IronManPassword2026!",
        },
    )
    assert reg_res.status_code == 201
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Reject invalid IAM Role ARN format
    bad_arn_res = client.post(
        "/api/v1/accounts/aws",
        headers=headers,
        json={"role_arn": "not-an-arn"},
    )
    assert bad_arn_res.status_code == 400
    assert "Invalid IAM Role ARN" in bad_arn_res.json()["detail"]

    # 2. Connect valid AWS IAM Role ARN
    valid_arn = "arn:aws:iam::123456789012:role/CloudGuardReadOnlyRole"
    conn_res = client.post(
        "/api/v1/accounts/aws",
        headers=headers,
        json={"role_arn": valid_arn, "alias": "Stark Production US-East"},
    )
    assert conn_res.status_code == 201
    conn_data = conn_res.json()
    assert conn_data["account_id"] == "123456789012"
    assert conn_data["role_arn"] == valid_arn
    assert conn_data["alias"] == "Stark Production US-East"
    assert conn_data["is_active"] is True

    # 3. List connected accounts
    list_res = client.get("/api/v1/accounts/aws", headers=headers)
    assert list_res.status_code == 200
    accounts = list_res.json()
    assert len(accounts) == 1
    assert accounts[0]["account_id"] == "123456789012"

    # 4. Connect same account again (idempotent, returns existing)
    dup_res = client.post(
        "/api/v1/accounts/aws",
        headers=headers,
        json={"role_arn": valid_arn, "alias": "Stark Production US-East"},
    )
    assert dup_res.status_code == 201
    assert dup_res.json()["id"] == conn_data["id"]

    # Clear dependency overrides
    app.dependency_overrides.clear()

