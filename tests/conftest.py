
#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Phase 1 test fixtures
=====================
Uses SQLite (aiosqlite) to avoid needing a real Postgres instance.
All tests get a fresh in-memory database per session.
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import os
import tempfile

from typing import AsyncGenerator

import pytest
import pytest_asyncio

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Point settings at SQLite before importing the app ────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true")
os.environ.setdefault("SECRET_KEY",   "test-secret-key-not-for-production")
os.environ.setdefault("ENVIRONMENT",  "testing")
os.environ.setdefault("ATTACHMENT_ROOT", tempfile.mkdtemp())

from app.core.database import Base, get_db, init_db
from app.main import create_app


# ── Shared engine (one per test session) ────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"

_engine = create_async_engine(TEST_DB_URL, echo=False, connect_args={"check_same_thread": False, "uri": True})
_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


# -----------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# -----------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables once per session, drop at teardown."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


# -----------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def clean_tables():
    """Truncate all data between tests."""
    yield
    async with _engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


# -----------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with _factory() as session:
        yield session


# -----------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with DB session override."""
    app = create_app()

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ── Convenience helpers ──────────────────────────────────────────────────────

async def create_user_and_token(client: AsyncClient, username="testuser", password="password123") -> tuple[dict, str]:
    """Register a user and return (user_data, access_token)."""
    r = await client.post("/api/v1/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": password,
        "display_name": username.capitalize(),
    })

    assert r.status_code == 201, r.text

    user = r.json()

    r2 = await client.post("/api/v1/auth/token", data={
        "username": username,
        "password": password,
    })

    assert r2.status_code == 200, r2.text

    token = r2.json()["access_token"]

    return user, token


# -----------------------------------------------------------------------------
