#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
ACL service
===========
Manage per-web and per-topic access control entries.

Principals:
  "user:jdoe"   — specific user
  "group:Dev"   — group membership (checked via user.groups)
  "*"           — everyone (including unauthenticated)

Permission evaluation:
  DENY entries take precedence over ALLOW entries.
  If no matching entry exists the default is:
    - view: ALLOW (public wiki by default)
    - everything else: DENY (require explicit grant)
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# -----------------------------------------------------------------------------

from app.models import ACL, User
from app.schemas import ACLUpdate


# -----------------------------------------------------------------------------

# Valid permissions
PERMISSIONS = frozenset({"view", "edit", "create", "rename", "delete", "admin"})
# Default-allow permissions (anything not in this set defaults to DENY)
DEFAULT_ALLOW = frozenset({"view"})


# -----------------------------------------------------------------------------

async def get_acl(
    db: AsyncSession,
    resource_type: str,
    resource_id: str,
) -> list[ACL]:
    result = await db.execute(
        select(ACL).where(ACL.resource_type == resource_type, ACL.resource_id == resource_id)
    )
    return list(result.scalars().all())


# -----------------------------------------------------------------------------

async def set_acl(
    db: AsyncSession,
    resource_type: str,
    resource_id: str,
    data: ACLUpdate,
) -> list[ACL]:
    """Replace all ACL entries for a resource."""
    # Delete existing entries
    existing = await get_acl(db, resource_type, resource_id)
    for entry in existing:
        await db.delete(entry)
    await db.flush()

    # Insert new entries
    new_entries = []
    for e in data.entries:
        if e.permission not in PERMISSIONS:
            raise HTTPException(status_code=400, detail=f"Unknown permission: {e.permission}")
        acl = ACL(
            resource_type=resource_type,
            resource_id=resource_id,
            principal=e.principal,
            permission=e.permission,
            allow=e.allow,
        )
        db.add(acl)
        new_entries.append(acl)

    await db.flush()
    return new_entries


# -----------------------------------------------------------------------------

async def check_permission(
    db: AsyncSession,
    resource_type: str,
    resource_id: str,
    permission: str,
    user: Optional[User] = None,
) -> bool:
    """
    Return True if *user* (or anonymous if None) has *permission* on the resource.
    """
    entries = await get_acl(db, resource_type, resource_id)
    if not entries:
        # No ACL configured → use defaults
        return permission in DEFAULT_ALLOW

    # Build principal set for this user
    principals: set[str] = {"*"}
    if user:
        principals.add(f"user:{user.username}")
        for g in user.groups_list():
            principals.add(f"group:{g}")
        if user.is_admin:
            return True   # admins bypass ACL

    # Evaluate: first collect matching DENY entries
    denies  = [e for e in entries if e.permission == permission and e.principal in principals and not e.allow]
    allows  = [e for e in entries if e.permission == permission and e.principal in principals and e.allow]

    if denies:
        return False
    if allows:
        return True

    # No explicit rule → default
    return permission in DEFAULT_ALLOW


# -----------------------------------------------------------------------------

async def require_permission(
    db: AsyncSession,
    resource_type: str,
    resource_id: str,
    permission: str,
    user: Optional[User] = None,
) -> None:
    """Raise HTTP 403 if the user lacks the permission."""
    allowed = await check_permission(db, resource_type, resource_id, permission, user)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: '{permission}' on {resource_type}:{resource_id}",
        )


# -----------------------------------------------------------------------------

