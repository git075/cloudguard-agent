"""
Unit & Integration Tests for Celery Scan Workers, Nightly Beat Scheduler, and FastAPI Scan Endpoints.
"""
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.models.db import Base, Customer, AWSAccount, ScanJob, PullRequestLog
from src.db.session import get_async_db, SyncSessionLocal
from src.services.auth import create_access_token, generate_external_id, hash_password
from src.jobs.scan_worker import execute_cloudguard_scan, run_nightly_scans
from src.api.scan_router import router as scan_router

app = FastAPI()
app.include_router(scan_router)


@pytest.fixture(autouse=True)
def setup_sync_test_db(monkeypatch):
    """Sets up an in-memory SQLite database for synchronous Celery worker testing."""
    test_sync_engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=test_sync_engine)
    TestSyncSession = sessionmaker(bind=test_sync_engine, autocommit=False, autoflush=False)

    monkeypatch.setattr("src.jobs.scan_worker.SyncSessionLocal", TestSyncSession)
    return TestSyncSession


@pytest_asyncio.fixture
async def async_test_session():
    """Provides an in-memory SQLite async database session for testing FastAPI scan router."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_celery_task_execution(setup_sync_test_db):
    """Tests synchronous execution of the Celery execute_cloudguard_scan task."""
    db = setup_sync_test_db()
    customer = Customer(
        name="Stark Industries",
        email="tony@stark.com",
        password_hash=hash_password("Jarvis123!"),
        external_id=generate_external_id(),
    )
    db.add(customer)
    db.commit()

    aws_account = AWSAccount(
        customer_id=customer.id,
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/CloudGuardRole",
    )
    db.add(aws_account)
    db.commit()

    scan_job = ScanJob(
        customer_id=customer.id,
        aws_account_id=aws_account.id,
        status="pending",
    )
    db.add(scan_job)
    db.commit()

    # Execute Celery scan worker directly
    res = execute_cloudguard_scan(scan_job_id=scan_job.id)
    assert res["status"] == "completed"
    assert res["resources_scanned"] == 1
    assert res["total_savings_usd"] == 1104.0

    # Query DB and verify scan job state
    db.refresh(scan_job)
    assert scan_job.status == "completed"
    assert scan_job.total_savings_identified == 1104.0

    pr_log = db.query(PullRequestLog).filter(PullRequestLog.scan_job_id == scan_job.id).first()
    assert pr_log is not None
    assert pr_log.proposed_spec == "db.r6g.xlarge"
    assert pr_log.monthly_savings_usd == 1104.0


def test_celery_beat_nightly_scans(setup_sync_test_db, monkeypatch):
    """Tests Celery Beat scheduled nightly scan dispatcher."""
    db = setup_sync_test_db()
    customer = Customer(
        name="Wayne Enterprises",
        email="bruce@wayne.com",
        password_hash=hash_password("Batcave123!"),
        external_id=generate_external_id(),
    )
    db.add(customer)
    db.commit()

    aws_account = AWSAccount(
        customer_id=customer.id,
        account_id="987654321098",
        role_arn="arn:aws:iam::987654321098:role/CloudGuardRole",
        is_active=True,
    )
    db.add(aws_account)
    db.commit()

    # Mock execute_cloudguard_scan.delay to avoid requiring live Redis broker in unit test
    class MockTask:
        id = "mock-task-12345"

    monkeypatch.setattr(
        "src.jobs.scan_worker.execute_cloudguard_scan.delay",
        lambda **kwargs: MockTask(),
    )

    res = run_nightly_scans()
    assert res["status"] == "success"
    assert res["dispatched_count"] == 1


@pytest.mark.asyncio
async def test_fastapi_scan_trigger_and_status_endpoints(async_test_session: AsyncSession, monkeypatch):
    """Tests FastAPI POST /api/v1/scans/trigger and GET /api/v1/scans/{id} endpoints."""
    # Seed test database
    customer = Customer(
        name="Oscorp",
        email="norman@oscorp.com",
        password_hash=hash_password("Pass123!"),
        external_id=generate_external_id(),
    )
    async_test_session.add(customer)
    await async_test_session.commit()

    aws_acc = AWSAccount(
        customer_id=customer.id,
        account_id="111122223333",
        role_arn="arn:aws:iam::111122223333:role/CloudGuardRole",
    )
    async_test_session.add(aws_acc)
    await async_test_session.commit()

    # Mock Celery delay to avoid requiring active Redis broker in unit test
    class MockTask:
        id = "celery-task-9999"

    monkeypatch.setattr(
        execute_cloudguard_scan,
        "delay",
        lambda **kwargs: MockTask(),
    )


    # Override async db dependency
    async def override_get_db():
        yield async_test_session

    app.dependency_overrides[get_async_db] = override_get_db
    client = TestClient(app)

    token = create_access_token(customer_id=customer.id, email=customer.email)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Trigger scan job via API
    trigger_res = client.post(
        "/api/v1/scans/trigger",
        json={"aws_account_id": aws_acc.id},
        headers=headers,
    )
    assert trigger_res.status_code == 202
    res_data = trigger_res.json()
    assert "scan_job_id" in res_data
    assert res_data["celery_task_id"] == "celery-task-9999"
    scan_job_id = res_data["scan_job_id"]


    # 2. Get status of triggered scan job
    status_res = client.get(f"/api/v1/scans/{scan_job_id}", headers=headers)
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["id"] == scan_job_id
    assert status_data["customer_id"] == customer.id

    # Clear overrides
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_fastapi_scan_tenant_isolation(async_test_session: AsyncSession):
    """Tests that Tenant A cannot trigger or view scans for Tenant B's AWS accounts."""
    cust_a = Customer(name="Tenant A", email="a@corp.com", password_hash="h", external_id=generate_external_id())
    cust_b = Customer(name="Tenant B", email="b@corp.com", password_hash="h", external_id=generate_external_id())
    async_test_session.add_all([cust_a, cust_b])
    await async_test_session.commit()

    acc_b = AWSAccount(customer_id=cust_b.id, account_id="222222222222", role_arn="arn:aws:iam::222222222222:role/R")
    async_test_session.add(acc_b)
    await async_test_session.commit()

    async def override_get_db():
        yield async_test_session

    app.dependency_overrides[get_async_db] = override_get_db
    client = TestClient(app)

    # Tenant A attempts to trigger scan for Tenant B's account
    token_a = create_access_token(customer_id=cust_a.id, email=cust_a.email)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    res = client.post("/api/v1/scans/trigger", json={"aws_account_id": acc_b.id}, headers=headers_a)
    assert res.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_fastapi_scan_trigger_celery_broker_down_returns_503(
    async_test_session: AsyncSession, monkeypatch
):
    """Verifies that if Celery broker is unavailable, endpoint returns HTTP 503 and marks scan job as failed."""
    customer = Customer(
        name="Broker Fail Tenant",
        email="broker_fail@corp.com",
        password_hash="hashed_pw",
        external_id=generate_external_id(),
    )
    async_test_session.add(customer)
    await async_test_session.commit()

    aws_acc = AWSAccount(
        customer_id=customer.id,
        account_id="333344445555",
        role_arn="arn:aws:iam::333344445555:role/FailRole",
    )
    async_test_session.add(aws_acc)
    await async_test_session.commit()

    def mock_fail_delay(**kwargs):
        raise ConnectionError("Redis broker connection refused")

    monkeypatch.setattr(execute_cloudguard_scan, "delay", mock_fail_delay)

    async def override_get_db():
        yield async_test_session

    app.dependency_overrides[get_async_db] = override_get_db
    client = TestClient(app)

    token = create_access_token(customer_id=customer.id, email=customer.email)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/v1/scans/trigger",
        json={"aws_account_id": aws_acc.id},
        headers=headers,
    )
    assert res.status_code == 503
    assert "Background task queue service is currently unavailable" in res.json()["detail"]

    # Verify ScanJob was saved with status='failed'
    stmt = select(ScanJob).where(ScanJob.customer_id == customer.id)
    scan_result = await async_test_session.execute(stmt)
    job = scan_result.scalars().first()
    assert job is not None
    assert job.status == "failed"
    assert "Redis broker connection refused" in job.error_message

    app.dependency_overrides.clear()

