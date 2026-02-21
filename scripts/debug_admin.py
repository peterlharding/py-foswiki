#!/usr/bin/env python
"""Debug script to verify admin promotion works across sessions."""
import asyncio
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ENVIRONMENT"] = "testing"
os.environ["ATTACHMENT_ROOT"] = tempfile.mkdtemp()

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import update, select
from app.core.database import Base
from app.models import User
from app.services.users import create_user
from app.schemas import UserCreate

engine = create_async_engine(
    "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true",
    echo=False,
    connect_args={"check_same_thread": False, "uri": True},
)
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def test():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Simulate registration (non-admin)
    async with factory() as db:
        u = await create_user(db, UserCreate(username="topicuser", email="t@x.com", password="pass1234"))
        await db.commit()
        print(f"after create is_admin={u.is_admin}, id={u.id}")

    # Promote to admin in separate session
    async with factory() as db2:
        await db2.execute(update(User).where(User.username == "topicuser").values(is_admin=True))
        await db2.commit()
        print("promotion committed")

    # Read back in new session
    async with factory() as db3:
        r = await db3.execute(select(User).where(User.username == "topicuser"))
        u2 = r.scalar_one_or_none()
        print(f"after promote is_admin={u2.is_admin if u2 else 'NOT FOUND'}")


asyncio.run(test())
