#!/usr/bin/env python
# -----------------------------------------------------------------------------
"""
Group service
=============
Groups are stored as comma-separated strings on the User.groups column.
This service provides a logical group abstraction over that storage.

A "group" is simply a name that appears in one or more users' groups field.
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


# -----------------------------------------------------------------------------

async def list_groups(db: AsyncSession) -> dict[str, list[User]]:
    """
    Return a dict mapping group_name → [User, ...], sorted by group name.
    Only groups that have at least one member are returned.
    """
    result = await db.execute(select(User).where(User.groups != "").order_by(User.username))
    users = result.scalars().all()

    groups: dict[str, list[User]] = defaultdict(list)
    for user in users:
        for g in user.groups_list():
            groups[g].append(user)

    return dict(sorted(groups.items(), key=lambda kv: kv[0].lower()))


# -----------------------------------------------------------------------------

async def get_group_members(db: AsyncSession, group_name: str) -> list[User]:
    """Return all users who are members of *group_name*."""
    result = await db.execute(select(User).order_by(User.username))
    users = result.scalars().all()
    return [u for u in users if group_name in u.groups_list()]


# -----------------------------------------------------------------------------

async def get_all_users(db: AsyncSession) -> list[User]:
    """Return all users, ordered by username."""
    result = await db.execute(select(User).order_by(User.username))
    return list(result.scalars().all())


# -----------------------------------------------------------------------------

async def add_member(db: AsyncSession, group_name: str, username: str) -> User | None:
    """Add *username* to *group_name*. Returns the updated User or None."""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        return None
    groups = user.groups_list()
    if group_name not in groups:
        groups.append(group_name)
        user.groups = ", ".join(sorted(groups))
    return user


# -----------------------------------------------------------------------------

async def remove_member(db: AsyncSession, group_name: str, username: str) -> User | None:
    """Remove *username* from *group_name*. Returns the updated User or None."""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        return None
    groups = [g for g in user.groups_list() if g != group_name]
    user.groups = ", ".join(sorted(groups))
    return user


# -----------------------------------------------------------------------------

async def rename_group(db: AsyncSession, old_name: str, new_name: str) -> int:
    """Rename a group across all users. Returns number of users updated."""
    result = await db.execute(select(User))
    users = result.scalars().all()
    count = 0
    for user in users:
        groups = user.groups_list()
        if old_name in groups:
            groups = [new_name if g == old_name else g for g in groups]
            user.groups = ", ".join(sorted(groups))
            count += 1
    return count


# -----------------------------------------------------------------------------

async def delete_group(db: AsyncSession, group_name: str) -> int:
    """Remove *group_name* from all users. Returns number of users updated."""
    result = await db.execute(select(User))
    users = result.scalars().all()
    count = 0
    for user in users:
        groups = user.groups_list()
        if group_name in groups:
            user.groups = ", ".join(sorted(g for g in groups if g != group_name))
            count += 1
    return count
