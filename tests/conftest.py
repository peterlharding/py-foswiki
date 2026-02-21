#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Test fixtures
=============
Uses SQLite (aiosqlite) with a shared-cache in-memory database.
One session-scoped engine; each test gets one AsyncSession shared between
the test helper and the HTTP client's get_db override.
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

# ── Env vars must be set before importing app modules ────────────────────────
os.environ.setdefault("DATABASE_URL",    "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY",      "test-secret-key-not-for-production")
os.environ.setdefault("ENVIRONMENT",     "testing")
os.environ.setdefault("ATTACHMENT_ROOT", tempfile.mkdtemp())

from app.core.database import Base, get_db
from app.main import create_app

# ── One engine, pool_size=1 so all sessions share the same connection ─────────
# SQLite shared-cache in-memory DB: one named DB visible to all connections
# in this process.  pool_size=1/max_overflow=0 means SQLAlchemy never opens
# a second connection, so every session sees every committed write immediately.
_TEST_URL = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"
_engine   = create_async_engine(
    _TEST_URL,
    echo=False,
    connect_args={"check_same_thread": False, "uri": True},
    pool_size=1,
    max_overflow=0,
)
_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


# ── Session-scoped event loop (required for session-scoped async fixtures) ────
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Create tables once for the whole test session ─────────────────────────────
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


# ── One AsyncSession per test ─────────────────────────────────────────────────
@pytest_asyncio.fixture
async def db(setup_database) -> AsyncGenerator[AsyncSession, None]:
    """Single AsyncSession shared by the test body and the HTTP client."""
    async with _factory() as session:
        yield session


# ── Wipe all rows after each test ─────────────────────────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def clean_tables(db: AsyncSession):
    yield
    for table in reversed(Base.metadata.sorted_tables):
        await db.execute(table.delete())
    await db.commit()


# ── HTTP client whose get_db uses the same session as the test ────────────────
@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with get_db overridden to the test's shared session."""
    app = create_app()

    async def _override_db():
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        # Attach the session so create_user_and_token can use it
        c._db = db  # type: ignore[attr-defined]
        yield c


# ── Helper: create a user + token using the test's shared session ─────────────

async def create_user_and_token(
    client: AsyncClient,
    username: str = "testuser",
    password: str = "password123",
    is_admin: bool = True,
) -> tuple[dict, str]:
    """Insert a user directly into the shared test session and return a token.

    Bypasses the registration API so there is no cross-session visibility
    issue.  Users are admins by default so ACL checks don't block tests
    written before Phase 4 ACL enforcement was added.
    """
    from sqlalchemy import select, text
    from app.models import User
    from app.core.security import hash_password
    from app.services.users import _wiki_name

    db: AsyncSession = client._db  # type: ignore[attr-defined]

    # Check if user already exists in this session
    result = await db.execute(select(User).where(User.username == username))
    existing = result.scalar_one_or_none()

    if existing is None:
        user = User(
            username=username,
            email=f"{username}@example.com",
            display_name=username.capitalize(),
            wiki_name=_wiki_name(username),
            password_hash=hash_password(password),
            is_admin=is_admin,
        )
        db.add(user)
        await db.flush()   # assign PK without closing the transaction
        user_id = user.id
    else:
        user_id = existing.id
        if is_admin and not existing.is_admin:
            await db.execute(
                text("UPDATE users SET is_admin = 1 WHERE id = :id"),
                {"id": user_id},
            )
        await db.flush()

    # Commit so the token endpoint (same session, re-entered) can read the row
    await db.commit()

    r = await client.post("/api/v1/auth/token", data={
        "username": username,
        "password": password,
    })
    assert r.status_code == 200, r.text
    return {"id": user_id, "username": username}, r.json()["access_token"]


# -----------------------------------------------------------------------------
