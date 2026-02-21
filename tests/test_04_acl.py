#!/usr/bin/env python
# -----------------------------------------------------------------------------
"""
Phase 4 — Access Control Tests
================================
  - ACL enforcement: non-admin users blocked by default, group-based access
  - Password reset: create token, validate, apply, expiry, single-use
  - Groups service: add/remove members, rename, delete
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import create_user_and_token

pytestmark = pytest.mark.asyncio


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Shared helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _admin_headers(client: AsyncClient, username: str = "admin1",
                         web: str | None = None) -> dict:
    _u, tok = await create_user_and_token(client, username, is_admin=True)
    h = {"Authorization": f"Bearer {tok}"}
    if web:
        r = await client.post("/api/v1/webs", json={"name": web}, headers=h)
        assert r.status_code in (201, 409), r.text
    return h


async def _create_topic(client, headers, web, name, content="content"):
    r = await client.post(
        f"/api/v1/webs/{web}/topics",
        json={"name": name, "content": content, "comment": "init"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ACL enforcement — non-admin users
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestACLEnforcement:
    async def _setup(self, client):
        admin_h = await _admin_headers(client, "aclowner", web="PrivateWeb")
        await _create_topic(client, admin_h, "PrivateWeb", "SecretTopic", "secret")
        _u2, user_tok = await create_user_and_token(client, "aclguest", is_admin=False)
        user_h = {"Authorization": f"Bearer {user_tok}"}
        return admin_h, user_h

    async def test_non_admin_cannot_create_topic_by_default(self, client: AsyncClient):
        _admin_h, user_h = await self._setup(client)
        r = await client.post("/api/v1/webs/PrivateWeb/topics",
                              json={"name": "Attempt", "content": "x"}, headers=user_h)
        assert r.status_code == 403

    async def test_non_admin_can_view_topic_by_default(self, client: AsyncClient):
        await self._setup(client)
        r = await client.get("/api/v1/webs/PrivateWeb/topics/SecretTopic")
        assert r.status_code == 200

    async def test_explicit_allow_grants_create(self, client: AsyncClient):
        admin_h, user_h = await self._setup(client)
        await client.put("/api/v1/webs/PrivateWeb/acl", json={"entries": [
            {"principal": "user:aclguest", "permission": "create", "allow": True},
        ]}, headers=admin_h)
        r = await client.post("/api/v1/webs/PrivateWeb/topics",
                              json={"name": "Allowed", "content": "x"}, headers=user_h)
        assert r.status_code == 201

    async def test_explicit_deny_blocks_view(self, client: AsyncClient):
        admin_h, user_h = await self._setup(client)
        await client.put("/api/v1/webs/PrivateWeb/acl", json={"entries": [
            {"principal": "user:aclguest", "permission": "view", "allow": False},
        ]}, headers=admin_h)
        r = await client.get("/api/v1/webs/PrivateWeb/topics/SecretTopic",
                             headers=user_h)
        assert r.status_code == 403

    async def test_deny_overrides_wildcard_allow(self, client: AsyncClient):
        admin_h, user_h = await self._setup(client)
        await client.put("/api/v1/webs/PrivateWeb/acl", json={"entries": [
            {"principal": "*",             "permission": "view", "allow": True},
            {"principal": "user:aclguest", "permission": "view", "allow": False},
        ]}, headers=admin_h)
        r = await client.get("/api/v1/webs/PrivateWeb/topics/SecretTopic",
                             headers=user_h)
        assert r.status_code == 403

    async def test_admin_bypasses_wildcard_deny(self, client: AsyncClient):
        admin_h, _user_h = await self._setup(client)
        await client.put("/api/v1/webs/PrivateWeb/acl", json={"entries": [
            {"principal": "*", "permission": "view", "allow": False},
        ]}, headers=admin_h)
        r = await client.get("/api/v1/webs/PrivateWeb/topics/SecretTopic",
                             headers=admin_h)
        assert r.status_code == 200

    async def test_group_based_allow_grants_create(self, client: AsyncClient):
        admin_h, user_h = await self._setup(client)
        from sqlalchemy import text
        db = client._db  # type: ignore[attr-defined]
        await db.execute(
            text("UPDATE users SET groups = 'Editors' WHERE username = 'aclguest'")
        )
        await db.commit()
        await client.put("/api/v1/webs/PrivateWeb/acl", json={"entries": [
            {"principal": "group:Editors", "permission": "create", "allow": True},
        ]}, headers=admin_h)
        r = await client.post("/api/v1/webs/PrivateWeb/topics",
                              json={"name": "GroupAllowed", "content": "x"},
                              headers=user_h)
        assert r.status_code == 201

    async def test_unauthenticated_cannot_create(self, client: AsyncClient):
        await self._setup(client)
        r = await client.post("/api/v1/webs/PrivateWeb/topics",
                              json={"name": "Anon", "content": "x"})
        assert r.status_code in (401, 403)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Password reset service (unit-level — no email transport)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPasswordReset:
    async def _setup(self, client):
        await create_user_and_token(client, "resetuser", "oldpassword", is_admin=False)

    async def test_create_reset_token(self, client: AsyncClient):
        await self._setup(client)
        from app.services.password_reset import create_reset_token
        db = client._db  # type: ignore[attr-defined]
        result = await create_reset_token(db, "resetuser@example.com")
        assert result is not None
        user, raw_token = result
        assert user.username == "resetuser"
        assert len(raw_token) > 20

    async def test_create_reset_token_unknown_email_returns_none(self, client: AsyncClient):
        from app.services.password_reset import create_reset_token
        db = client._db  # type: ignore[attr-defined]
        result = await create_reset_token(db, "nobody@example.com")
        assert result is None

    async def test_validate_reset_token(self, client: AsyncClient):
        await self._setup(client)
        from app.services.password_reset import create_reset_token, validate_reset_token
        db = client._db  # type: ignore[attr-defined]
        _, raw_token = await create_reset_token(db, "resetuser@example.com")
        await db.commit()
        user = await validate_reset_token(db, raw_token)
        assert user.username == "resetuser"

    async def test_validate_invalid_token_raises_400(self, client: AsyncClient):
        from app.services.password_reset import validate_reset_token
        from fastapi import HTTPException
        db = client._db  # type: ignore[attr-defined]
        with pytest.raises(HTTPException) as exc:
            await validate_reset_token(db, "not-a-real-token")
        assert exc.value.status_code == 400

    async def test_apply_reset_changes_password(self, client: AsyncClient):
        await self._setup(client)
        from app.services.password_reset import apply_reset_token, create_reset_token
        db = client._db  # type: ignore[attr-defined]
        _, raw_token = await create_reset_token(db, "resetuser@example.com")
        await db.commit()
        await apply_reset_token(db, raw_token, "newpassword456")
        await db.commit()
        # Old password must fail
        r = await client.post("/api/v1/auth/token",
                              data={"username": "resetuser", "password": "oldpassword"})
        assert r.status_code == 401
        # New password must succeed
        r2 = await client.post("/api/v1/auth/token",
                               data={"username": "resetuser", "password": "newpassword456"})
        assert r2.status_code == 200

    async def test_token_is_single_use(self, client: AsyncClient):
        await self._setup(client)
        from app.services.password_reset import apply_reset_token, create_reset_token
        from fastapi import HTTPException
        db = client._db  # type: ignore[attr-defined]
        _, raw_token = await create_reset_token(db, "resetuser@example.com")
        await db.commit()
        await apply_reset_token(db, raw_token, "newpassword456")
        await db.commit()
        with pytest.raises(HTTPException) as exc:
            await apply_reset_token(db, raw_token, "anotherpassword")
        assert exc.value.status_code == 400

    async def test_expired_token_rejected(self, client: AsyncClient):
        await self._setup(client)
        from datetime import datetime, timedelta, timezone
        from app.services.password_reset import create_reset_token, validate_reset_token
        from app.models import PasswordResetToken
        from fastapi import HTTPException
        from sqlalchemy import select
        db = client._db  # type: ignore[attr-defined]
        _, raw_token = await create_reset_token(db, "resetuser@example.com")
        result = await db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token == raw_token)
        )
        token_obj = result.scalar_one()
        token_obj.expires_at = datetime.now(tz=timezone.utc) - timedelta(hours=2)
        await db.commit()
        with pytest.raises(HTTPException) as exc:
            await validate_reset_token(db, raw_token)
        assert exc.value.status_code == 400
        assert "expired" in exc.value.detail.lower()

    async def test_second_create_invalidates_first_token(self, client: AsyncClient):
        await self._setup(client)
        from app.services.password_reset import create_reset_token, validate_reset_token
        from fastapi import HTTPException
        db = client._db  # type: ignore[attr-defined]
        _, tok1 = await create_reset_token(db, "resetuser@example.com")
        await db.commit()
        _, tok2 = await create_reset_token(db, "resetuser@example.com")
        await db.commit()
        # First token should now be invalid
        with pytest.raises(HTTPException) as exc:
            await validate_reset_token(db, tok1)
        assert exc.value.status_code == 400
        # Second token should still be valid
        user = await validate_reset_token(db, tok2)
        assert user.username == "resetuser"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Groups service
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestGroupsService:
    """Tests call the service layer directly via the shared test session."""

    async def _create_users(self, client):
        await create_user_and_token(client, "alice", is_admin=False)
        await create_user_and_token(client, "bob",   is_admin=False)
        return client._db  # type: ignore[attr-defined]

    async def test_add_member_to_group(self, client: AsyncClient):
        from app.services.groups import add_member, get_group_members
        db = await self._create_users(client)
        user = await add_member(db, "Editors", "alice")
        await db.commit()
        assert user is not None
        members = await get_group_members(db, "Editors")
        assert any(u.username == "alice" for u in members)

    async def test_add_member_idempotent(self, client: AsyncClient):
        from app.services.groups import add_member, get_group_members
        db = await self._create_users(client)
        await add_member(db, "Editors", "alice")
        await add_member(db, "Editors", "alice")
        await db.commit()
        members = await get_group_members(db, "Editors")
        assert sum(1 for u in members if u.username == "alice") == 1

    async def test_add_member_unknown_user_returns_none(self, client: AsyncClient):
        from app.services.groups import add_member
        db = await self._create_users(client)
        result = await add_member(db, "Editors", "nobody")
        assert result is None

    async def test_remove_member_from_group(self, client: AsyncClient):
        from app.services.groups import add_member, remove_member, get_group_members
        db = await self._create_users(client)
        await add_member(db, "Editors", "alice")
        await db.commit()
        await remove_member(db, "Editors", "alice")
        await db.commit()
        members = await get_group_members(db, "Editors")
        assert not any(u.username == "alice" for u in members)

    async def test_remove_member_not_in_group_is_safe(self, client: AsyncClient):
        from app.services.groups import remove_member
        db = await self._create_users(client)
        user = await remove_member(db, "Editors", "alice")
        assert user is not None  # user found, just not in group

    async def test_remove_member_unknown_user_returns_none(self, client: AsyncClient):
        from app.services.groups import remove_member
        db = await self._create_users(client)
        result = await remove_member(db, "Editors", "nobody")
        assert result is None

    async def test_list_groups(self, client: AsyncClient):
        from app.services.groups import add_member, list_groups
        db = await self._create_users(client)
        await add_member(db, "Editors", "alice")
        await add_member(db, "Reviewers", "bob")
        await db.commit()
        groups = await list_groups(db)
        assert "Editors" in groups
        assert "Reviewers" in groups
        assert any(u.username == "alice" for u in groups["Editors"])
        assert any(u.username == "bob"   for u in groups["Reviewers"])

    async def test_list_groups_empty_when_no_members(self, client: AsyncClient):
        from app.services.groups import list_groups
        db = await self._create_users(client)
        groups = await list_groups(db)
        assert groups == {}

    async def test_get_group_members_empty_group(self, client: AsyncClient):
        from app.services.groups import get_group_members
        db = await self._create_users(client)
        members = await get_group_members(db, "NonExistent")
        assert members == []

    async def test_rename_group(self, client: AsyncClient):
        from app.services.groups import add_member, rename_group, get_group_members
        db = await self._create_users(client)
        await add_member(db, "OldName", "alice")
        await add_member(db, "OldName", "bob")
        await db.commit()
        count = await rename_group(db, "OldName", "NewName")
        await db.commit()
        assert count == 2
        assert await get_group_members(db, "OldName") == []
        new_members = await get_group_members(db, "NewName")
        assert len(new_members) == 2

    async def test_rename_nonexistent_group_returns_zero(self, client: AsyncClient):
        from app.services.groups import rename_group
        db = await self._create_users(client)
        count = await rename_group(db, "Ghost", "Phantom")
        assert count == 0

    async def test_delete_group(self, client: AsyncClient):
        from app.services.groups import add_member, delete_group, get_group_members
        db = await self._create_users(client)
        await add_member(db, "ToDelete", "alice")
        await add_member(db, "ToDelete", "bob")
        await db.commit()
        count = await delete_group(db, "ToDelete")
        await db.commit()
        assert count == 2
        assert await get_group_members(db, "ToDelete") == []

    async def test_delete_nonexistent_group_returns_zero(self, client: AsyncClient):
        from app.services.groups import delete_group
        db = await self._create_users(client)
        count = await delete_group(db, "Ghost")
        assert count == 0

    async def test_user_can_belong_to_multiple_groups(self, client: AsyncClient):
        from app.services.groups import add_member, get_group_members
        db = await self._create_users(client)
        await add_member(db, "Editors",   "alice")
        await add_member(db, "Reviewers", "alice")
        await db.commit()
        editors   = await get_group_members(db, "Editors")
        reviewers = await get_group_members(db, "Reviewers")
        assert any(u.username == "alice" for u in editors)
        assert any(u.username == "alice" for u in reviewers)
