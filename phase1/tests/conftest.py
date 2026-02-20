#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Shared pytest fixtures.
Uses an in-memory SQLite database for fast, isolated tests.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ── allow running from tests/ dir ──────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override DB before any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["DEBUG"] = "true"

from app.core.database import Base, get_db
from app.main import app

# ── SQLite test engine ──────────────────────────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
_TestSession = async_sessionmaker(
    bind=_test_engine, class_=AsyncSession,
    expire_on_commit=False, autocommit=False, autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all tables once per test session."""
    import app.models  # noqa: F401 — register models
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def clean_tables():
    """Truncate all tables between tests for isolation."""
    yield
    async with _test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session that is rolled back after each test."""
    async with _TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP test client with the test DB session injected.
    """
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ─────────────────────────────────────────────────────────────────

async def register_and_login(client: AsyncClient, username="testuser", password="TestPass123!") -> str:
    """Create a user and return their JWT token."""
    await client.post("/api/v1/auth/register", json={
        "username": username,
        "email": f"{username}@test.com",
        "display_name": username.capitalize(),
        "password": password,
    })
    resp = await client.post("/api/v1/auth/login", data={
        "username": username,
        "password": password,
    })
    return resp.json()["access_token"]


async def auth_headers(client: AsyncClient, username="testuser") -> dict:
    token = await register_and_login(client, username)
    return {"Authorization": f"Bearer {token}"}



