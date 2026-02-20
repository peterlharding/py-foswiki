#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
User service — account creation, lookup, password management.
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# -----------------------------------------------------------------------------

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas import UserCreate, UserUpdate


# -----------------------------------------------------------------------------

def _wiki_name(username: str) -> str:
    """Convert 'john_doe' → 'JohnDoe' (CamelCase wiki name)."""
    parts = re.split(r"[_.\-]+", username)
    return "".join(p.capitalize() for p in parts)


# -----------------------------------------------------------------------------

async def create_user(db: AsyncSession, data: UserCreate) -> User:
    # Check uniqueness
    existing = await db.execute(
        select(User).where(
            (User.username == data.username) | (User.email == data.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    display = data.display_name or data.username
    user = User(
        username=data.username,
        email=str(data.email),
        display_name=display,
        wiki_name=_wiki_name(data.username),
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    return user


# -----------------------------------------------------------------------------

async def get_user_by_id(db: AsyncSession, user_id: str) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# -----------------------------------------------------------------------------

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


# -----------------------------------------------------------------------------

async def authenticate_user(db: AsyncSession, username: str, password: str) -> User:
    user = await get_user_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return user


# -----------------------------------------------------------------------------

async def update_user(db: AsyncSession, user_id: str, data: UserUpdate) -> User:
    user = await get_user_by_id(db, user_id)
    if data.email is not None:
        user.email = str(data.email)
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.password is not None:
        user.password_hash = hash_password(data.password)
    await db.flush()
    return user


# -----------------------------------------------------------------------------

async def list_users(db: AsyncSession, skip: int = 0, limit: int = 50) -> list[User]:
    result = await db.execute(select(User).offset(skip).limit(limit))
    return list(result.scalars().all())


# -----------------------------------------------------------------------------

async def change_password(
    db: AsyncSession, user_id: str, old_password: str, new_password: str
) -> User:
    user = await get_user_by_id(db, user_id)
    if not verify_password(old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(new_password)
    await db.flush()
    return user


# -----------------------------------------------------------------------------

async def set_active(db: AsyncSession, username: str, is_active: bool) -> User:
    user = await get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    user.is_active = is_active
    await db.flush()
    return user


# -----------------------------------------------------------------------------

async def delete_user(db: AsyncSession, username: str) -> None:
    user = await get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    await db.delete(user)
    await db.flush()


# -----------------------------------------------------------------------------

async def set_admin(db: AsyncSession, username: str, is_admin: bool) -> User:
    user = await get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    user.is_admin = is_admin
    await db.flush()
    return user


# -----------------------------------------------------------------------------

