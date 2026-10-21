"""
Database Session Management for CloudGuard FinOps.
Provides engine creation, sessionmakers (async and sync), and table initialization helpers.
"""
import os
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from src.models.db import Base

# Database URL from environment variable or default SQLite database for testing/dev
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./cloudguard.db")
SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL", "sqlite:///./cloudguard.db")

# Async Engine & Sessionmaker
is_async_sqlite = "sqlite" in DATABASE_URL
async_kwargs = {"echo": False, "future": True}
if is_async_sqlite:
    async_kwargs["connect_args"] = {"check_same_thread": False}
else:
    async_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
        "pool_timeout": 30,
    })
async_engine = create_async_engine(DATABASE_URL, **async_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Sync Engine & Sessionmaker (for Celery workers & migrations)
is_sync_sqlite = "sqlite" in SYNC_DATABASE_URL
sync_kwargs = {"echo": False}
if is_sync_sqlite:
    sync_kwargs["connect_args"] = {"check_same_thread": False}
else:
    sync_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
        "pool_timeout": 30,
    })
sync_engine = create_engine(SYNC_DATABASE_URL, **sync_kwargs)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)


async def init_db():
    """Initializes all database tables async (creates tables if they do not exist)."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def init_db_sync():
    """Initializes all database tables synchronously."""
    Base.metadata.create_all(bind=sync_engine)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for providing async DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db() -> Generator[Session, None, None]:
    """Sync DB session generator for synchronous tasks."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
