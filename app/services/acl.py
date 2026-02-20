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

# Permission hierarchy: granting a higher permission implies all lower ones.
# e.g. if a user has ALLOW edit, they implicitly have ALLOW view.
_IMPLIED_BY: dict[str, frozenset[str]] = {
    "view":   frozenset({"edit", "create", "rename", "delete", "admin"}),
    "edit":   frozenset({"rename", "delete", "admin"}),
    "create": frozenset({"admin"}),
    "rename": frozenset({"admin"}),
    "delete": frozenset({"admin"}),
    "admin":  frozenset(),
}


def _expand_permission(permission: str) -> frozenset[str]:
    """Return the set of permissions that imply *permission* (including itself)."""
    return frozenset({permission}) | _IMPLIED_BY.get(permission, frozenset())


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

def _eval_entries(
    entries: list,
    permission: str,
    principals: set[str],
) -> Optional[bool]:
    """
    Evaluate a list of ACL entries for a given permission and principal set.
    Returns True (allow), False (deny), or None (no matching rule).
    DENY takes precedence over ALLOW.

    Permission hierarchy: an ALLOW on a higher permission implies the lower one.
    e.g. ALLOW edit → implicitly ALLOW view.
    DENY is never implied — only explicit DENY entries deny.
    """
    implied = _expand_permission(permission)  # set of permissions that imply this one

    # Explicit DENY on the exact permission only (DENY is never implied)
    denies = [e for e in entries if e.permission == permission and e.principal in principals and not e.allow]
    # ALLOW on the exact permission OR any higher permission that implies it
    allows = [e for e in entries if e.permission in implied and e.principal in principals and e.allow]
    if denies:
        return False
    if allows:
        return True
    return None


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

    result = _eval_entries(entries, permission, principals)
    if result is not None:
        return result

    # No explicit rule → default
    return permission in DEFAULT_ALLOW


async def check_topic_permission(
    db: AsyncSession,
    topic_id: str,
    web_id: str,
    permission: str,
    user: Optional[User] = None,
) -> bool:
    """
    Check permission on a topic, falling back to the web ACL if no topic-level
    ACL is configured (Foswiki-style inheritance).
    """
    if user and user.is_admin:
        return True

    principals: set[str] = {"*"}
    if user:
        principals.add(f"user:{user.username}")
        for g in user.groups_list():
            principals.add(f"group:{g}")

    # 1. Check topic-level ACL first
    topic_entries = await get_acl(db, "topic", topic_id)
    if topic_entries:
        result = _eval_entries(topic_entries, permission, principals)
        if result is not None:
            return result
        return permission in DEFAULT_ALLOW

    # 2. Fall back to web-level ACL
    web_entries = await get_acl(db, "web", web_id)
    if web_entries:
        result = _eval_entries(web_entries, permission, principals)
        if result is not None:
            return result
        return permission in DEFAULT_ALLOW

    # 3. No ACL at either level → defaults
    return permission in DEFAULT_ALLOW


async def require_topic_permission(
    db: AsyncSession,
    topic_id: str,
    web_id: str,
    permission: str,
    user: Optional[User] = None,
) -> None:
    """Raise HTTP 403 if the user lacks *permission* on the topic (with web fallback)."""
    allowed = await check_topic_permission(db, topic_id, web_id, permission, user)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: '{permission}' on this topic",
        )


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

