#!/usr/bin/env python
"""Debug script to simulate the full test flow."""
import asyncio
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ENVIRONMENT"] = "testing"
os.environ["ATTACHMENT_ROOT"] = tempfile.mkdtemp()

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import update, select
from httpx import ASGITransport, AsyncClient
from app.core.database import Base, get_db
from app.main import create_app
from app.models import User

engine = create_async_engine(
    "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true",
    echo=False,
    connect_args={"check_same_thread": False, "uri": True},
)
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def test():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async def _override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register
        r = await client.post("/api/v1/auth/register", json={
            "username": "topicuser",
            "email": "t@x.com",
            "password": "pass1234",
            "display_name": "Topicuser",
        })
        print(f"register: {r.status_code} {r.json()}")

        # Promote to admin
        async with factory() as db:
            result = await db.execute(select(User).where(User.username == "topicuser"))
            u = result.scalar_one_or_none()
            print(f"before promote: is_admin={u.is_admin if u else 'NOT FOUND'}, id={u.id if u else 'N/A'}")
            await db.execute(update(User).where(User.username == "topicuser").values(is_admin=True))
            await db.commit()

        # Verify in new session
        async with factory() as db2:
            result2 = await db2.execute(select(User).where(User.username == "topicuser"))
            u2 = result2.scalar_one_or_none()
            print(f"after promote: is_admin={u2.is_admin if u2 else 'NOT FOUND'}")

        # Login
        r2 = await client.post("/api/v1/auth/token", data={"username": "topicuser", "password": "pass1234"})
        print(f"login: {r2.status_code}")
        token = r2.json()["access_token"]

        # Create web
        r3 = await client.post("/api/v1/webs", json={"name": "TestWeb"}, headers={"Authorization": f"Bearer {token}"})
        print(f"create web: {r3.status_code} {r3.json()}")

        # Create topic
        r4 = await client.post("/api/v1/webs/TestWeb/topics", json={
            "name": "WebHome", "content": "hello", "comment": "test"
        }, headers={"Authorization": f"Bearer {token}"})
        print(f"create topic: {r4.status_code} {r4.json()}")


asyncio.run(test())
