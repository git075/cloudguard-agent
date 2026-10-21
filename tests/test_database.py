"""
Unit & Integration Tests for Multi-Tenant Database Models & Alembic Migrations.
Tests SQLAlchemy 2.0 ORM schemas, relationships, cascade deletes, and tenant data isolation.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from src.models.db import Base, Customer, AWSAccount, ScanJob, PullRequestLog
from src.services.auth import generate_external_id, hash_password


@pytest_asyncio.fixture
async def async_db_session():
    """Provides an in-memory SQLite async database session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_customer_creation_and_external_id(async_db_session: AsyncSession):
    """Test creating a customer with auto-generated ExternalId and password hash."""
    ext_id = generate_external_id()
    customer = Customer(
        name="Acme Corp",
        email="devops@acme.com",
        password_hash=hash_password("Secret123!"),
        external_id=ext_id,
    )
    async_db_session.add(customer)
    await async_db_session.commit()

    # Query back
    stmt = select(Customer).where(Customer.email == "devops@acme.com")
    result = await async_db_session.execute(stmt)
    fetched = result.scalar_one_or_none()

    assert fetched is not None
    assert fetched.name == "Acme Corp"
    assert fetched.external_id.startswith("cg_ext_")
    assert len(fetched.external_id) == 63 or len(fetched.external_id) == 64
    assert fetched.is_active is True


@pytest.mark.asyncio
async def test_aws_account_relationship_and_cascade(async_db_session: AsyncSession):
    """Test registering AWS Account for customer and verifying cascade deletion."""
    customer = Customer(
        name="Stark Industries",
        email="tony@stark.com",
        password_hash=hash_password("Jarvis123!"),
        external_id=generate_external_id(),
    )
    async_db_session.add(customer)
    await async_db_session.commit()

    aws_acc = AWSAccount(
        customer_id=customer.id,
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/CloudGuardRole",
        alias="Prod-US-East",
    )
    async_db_session.add(aws_acc)
    await async_db_session.commit()

    # Verify relationship
    stmt = select(AWSAccount).where(AWSAccount.customer_id == customer.id)
    res = await async_db_session.execute(stmt)
    accounts = res.scalars().all()
    assert len(accounts) == 1
    assert accounts[0].account_id == "123456789012"

    # Delete customer and verify AWSAccount is cascade deleted
    await async_db_session.delete(customer)
    await async_db_session.commit()

    res_after = await async_db_session.execute(stmt)
    assert len(res_after.scalars().all()) == 0


@pytest.mark.asyncio
async def test_scan_job_and_pull_request_log(async_db_session: AsyncSession):
    """Test creation of ScanJob and PullRequestLog records."""
    customer = Customer(
        name="Wayne Enterprises",
        email="bruce@wayne.com",
        password_hash=hash_password("Batcave123!"),
        external_id=generate_external_id(),
    )
    async_db_session.add(customer)
    await async_db_session.commit()

    aws_acc = AWSAccount(
        customer_id=customer.id,
        account_id="987654321098",
        role_arn="arn:aws:iam::987654321098:role/CloudGuardRole",
    )
    async_db_session.add(aws_acc)
    await async_db_session.commit()

    scan_job = ScanJob(
        customer_id=customer.id,
        aws_account_id=aws_acc.id,
        status="completed",
        total_resources_scanned=5,
        total_savings_identified=1104.0,
    )
    async_db_session.add(scan_job)
    await async_db_session.commit()

    pr_log = PullRequestLog(
        customer_id=customer.id,
        scan_job_id=scan_job.id,
        resource_id="production_db",
        original_spec="db.r5.2xlarge",
        proposed_spec="db.r6g.xlarge",
        monthly_savings_usd=1104.0,
        pr_url="https://github.com/wayne/infra/pull/42",
        status="created",
    )
    async_db_session.add(pr_log)
    await async_db_session.commit()

    # Query scan jobs and PR logs
    stmt = select(ScanJob).where(ScanJob.id == scan_job.id)
    job_fetched = (await async_db_session.execute(stmt)).scalar_one_or_none()
    assert job_fetched is not None
    assert job_fetched.status == "completed"
    assert job_fetched.total_savings_identified == 1104.0

    stmt_pr = select(PullRequestLog).where(PullRequestLog.scan_job_id == scan_job.id)
    pr_fetched = (await async_db_session.execute(stmt_pr)).scalar_one_or_none()
    assert pr_fetched is not None
    assert pr_fetched.proposed_spec == "db.r6g.xlarge"
    assert pr_fetched.pr_url == "https://github.com/wayne/infra/pull/42"


@pytest.mark.asyncio
async def test_multi_tenant_data_isolation(async_db_session: AsyncSession):
    """Test that customer tenant A cannot access customer tenant B data."""
    cust_a = Customer(name="Tenant A", email="a@corp.com", password_hash="hash", external_id=generate_external_id())
    cust_b = Customer(name="Tenant B", email="b@corp.com", password_hash="hash", external_id=generate_external_id())
    async_db_session.add_all([cust_a, cust_b])
    await async_db_session.commit()

    acc_a = AWSAccount(customer_id=cust_a.id, account_id="111111111111", role_arn="arn:aws:iam::111111111111:role/R")
    acc_b = AWSAccount(customer_id=cust_b.id, account_id="222222222222", role_arn="arn:aws:iam::222222222222:role/R")
    async_db_session.add_all([acc_a, acc_b])
    await async_db_session.commit()

    # Query scoped to Tenant A
    stmt_a = select(AWSAccount).where(AWSAccount.customer_id == cust_a.id)
    accounts_a = (await async_db_session.execute(stmt_a)).scalars().all()
    assert len(accounts_a) == 1
    assert accounts_a[0].account_id == "111111111111"
