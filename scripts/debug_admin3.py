#!/usr/bin/env python
"""Debug: check what db.get returns after admin promotion."""
import asyncio
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ENVIRONMENT"] = "testing"
os.environ["ATTACHMENT_ROOT"] = tempfile.mkdtemp()

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import update, select, text
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

    user_id = None

    # Session 1: create user
    async with factory() as db:
        u = await create_user(db, UserCreate(username="topicuser", email="t@x.com", password="pass1234"))
        await db.commit()
        user_id = u.id
        print(f"created: id={user_id}, is_admin={u.is_admin}")

    # Session 2: promote
    async with factory() as db2:
        await db2.execute(update(User).where(User.username == "topicuser").values(is_admin=True))
        await db2.commit()
        print("promoted")

    # Session 3: db.get() by primary key
    async with factory() as db3:
        u3 = await db3.get(User, user_id)
        print(f"db.get: is_admin={u3.is_admin if u3 else 'NOT FOUND'}")

    # Session 4: raw SQL
    async with factory() as db4:
        r = await db4.execute(text(f"SELECT is_admin FROM users WHERE id='{user_id}'"))
        row = r.fetchone()
        print(f"raw SQL: is_admin={row[0] if row else 'NOT FOUND'}")


asyncio.run(test())
