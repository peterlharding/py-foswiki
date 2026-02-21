#!/usr/bin/env python
# -----------------------------------------------------------------------------
"""
Phase 6 — Admin API Tests
==========================
  - Statistics endpoint
  - Site config read / update
  - User management: list, search, get, activate, deactivate, delete
  - Plugin listing
  - All endpoints require admin auth (403 for non-admin)
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import create_user_and_token

pytestmark = pytest.mark.asyncio


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _admin(client: AsyncClient, username: str = "siteadmin") -> dict:
    _u, tok = await create_user_and_token(client, username, is_admin=True)
    return {"Authorization": f"Bearer {tok}"}


async def _nonadmin(client: AsyncClient, username: str = "plainuser") -> dict:
    _u, tok = await create_user_and_token(client, username, is_admin=False)
    return {"Authorization": f"Bearer {tok}"}


async def _register(client: AsyncClient, username: str, password: str = "password123"):
    r = await client.post("/api/v1/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": password,
    })
    assert r.status_code == 201, r.text
    return r.json()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Statistics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAdminStats:
    async def test_stats_returns_200(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/stats", headers=h)
        assert r.status_code == 200

    async def test_stats_has_required_fields(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/stats", headers=h)
        body = r.json()
        for field in ("user_count", "admin_count", "inactive_user_count",
                      "web_count", "topic_count", "version_count"):
            assert field in body

    async def test_stats_counts_are_non_negative(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/stats", headers=h)
        body = r.json()
        for field in ("user_count", "admin_count", "web_count", "topic_count"):
            assert body[field] >= 0

    async def test_stats_reflects_created_user(self, client: AsyncClient):
        h = await _admin(client)
        before = (await client.get("/api/v1/admin/stats", headers=h)).json()["user_count"]
        await _register(client, "statsuser1")
        after = (await client.get("/api/v1/admin/stats", headers=h)).json()["user_count"]
        assert after == before + 1

    async def test_stats_reflects_created_web(self, client: AsyncClient):
        h = await _admin(client)
        before = (await client.get("/api/v1/admin/stats", headers=h)).json()["web_count"]
        await client.post("/api/v1/webs", json={"name": "StatsWeb"}, headers=h)
        after = (await client.get("/api/v1/admin/stats", headers=h)).json()["web_count"]
        assert after == before + 1

    async def test_stats_admin_count_correct(self, client: AsyncClient):
        h = await _admin(client)
        body = (await client.get("/api/v1/admin/stats", headers=h)).json()
        assert body["admin_count"] >= 1

    async def test_stats_requires_admin(self, client: AsyncClient):
        h = await _nonadmin(client)
        r = await client.get("/api/v1/admin/stats", headers=h)
        assert r.status_code == 403

    async def test_stats_requires_auth(self, client: AsyncClient):
        r = await client.get("/api/v1/admin/stats")
        assert r.status_code == 401


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Site config
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAdminConfig:
    async def test_get_config_returns_200(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/config", headers=h)
        assert r.status_code == 200

    async def test_get_config_has_required_fields(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/config", headers=h)
        body = r.json()
        for field in ("site_name", "base_url", "allow_registration",
                      "default_web", "admin_email", "app_version", "environment"):
            assert field in body

    async def test_update_site_name(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.put("/api/v1/admin/config",
                             json={"site_name": "MyWiki"}, headers=h)
        assert r.status_code == 200
        assert r.json()["site_name"] == "MyWiki"

    async def test_update_allow_registration(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.put("/api/v1/admin/config",
                             json={"allow_registration": False}, headers=h)
        assert r.status_code == 200
        assert r.json()["allow_registration"] is False
        # restore
        await client.put("/api/v1/admin/config",
                         json={"allow_registration": True}, headers=h)

    async def test_update_admin_email(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.put("/api/v1/admin/config",
                             json={"admin_email": "newadmin@example.com"}, headers=h)
        assert r.status_code == 200
        assert r.json()["admin_email"] == "newadmin@example.com"

    async def test_update_default_web(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.put("/api/v1/admin/config",
                             json={"default_web": "Wiki"}, headers=h)
        assert r.status_code == 200
        assert r.json()["default_web"] == "Wiki"

    async def test_partial_update_leaves_other_fields(self, client: AsyncClient):
        h = await _admin(client)
        before = (await client.get("/api/v1/admin/config", headers=h)).json()
        await client.put("/api/v1/admin/config",
                         json={"site_name": "PartialUpdate"}, headers=h)
        after = (await client.get("/api/v1/admin/config", headers=h)).json()
        assert after["site_name"] == "PartialUpdate"
        assert after["allow_registration"] == before["allow_registration"]

    async def test_config_requires_admin(self, client: AsyncClient):
        h = await _nonadmin(client)
        assert (await client.get("/api/v1/admin/config", headers=h)).status_code == 403
        assert (await client.put("/api/v1/admin/config",
                                 json={"site_name": "X"}, headers=h)).status_code == 403

    async def test_config_requires_auth(self, client: AsyncClient):
        assert (await client.get("/api/v1/admin/config")).status_code == 401


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. User management
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAdminUsers:
    async def test_list_users_returns_200(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/users", headers=h)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_list_users_includes_is_active(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/users", headers=h)
        users = r.json()
        assert users
        assert "is_active" in users[0]

    async def test_list_users_pagination(self, client: AsyncClient):
        h = await _admin(client)
        for i in range(3):
            await _register(client, f"pguser{i}")
        r1 = await client.get("/api/v1/admin/users?limit=2", headers=h)
        assert len(r1.json()) <= 2
        r2 = await client.get("/api/v1/admin/users?skip=0&limit=1", headers=h)
        assert len(r2.json()) == 1

    async def test_list_users_search_by_username(self, client: AsyncClient):
        h = await _admin(client)
        await _register(client, "uniqueusername99")
        r = await client.get("/api/v1/admin/users?search=uniqueusername99", headers=h)
        assert any(u["username"] == "uniqueusername99" for u in r.json())

    async def test_list_users_search_no_match(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/users?search=xyzzy_no_match", headers=h)
        assert r.json() == []

    async def test_get_user_by_username(self, client: AsyncClient):
        h = await _admin(client)
        await _register(client, "getmeuser")
        r = await client.get("/api/v1/admin/users/getmeuser", headers=h)
        assert r.status_code == 200
        assert r.json()["username"] == "getmeuser"

    async def test_get_user_not_found(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/users/nobody_here", headers=h)
        assert r.status_code == 404

    async def test_deactivate_user(self, client: AsyncClient):
        h = await _admin(client)
        await _register(client, "deactivateme")
        r = await client.patch("/api/v1/admin/users/deactivateme/deactivate", headers=h)
        assert r.status_code == 200
        assert r.json()["is_active"] is False

    async def test_activate_user(self, client: AsyncClient):
        h = await _admin(client)
        await _register(client, "activateme")
        await client.patch("/api/v1/admin/users/activateme/deactivate", headers=h)
        r = await client.patch("/api/v1/admin/users/activateme/activate", headers=h)
        assert r.status_code == 200
        assert r.json()["is_active"] is True

    async def test_deactivated_user_cannot_login(self, client: AsyncClient):
        h = await _admin(client)
        await _register(client, "lockedout")
        await client.patch("/api/v1/admin/users/lockedout/deactivate", headers=h)
        r = await client.post("/api/v1/auth/token",
                              data={"username": "lockedout", "password": "password123"})
        assert r.status_code == 403

    async def test_delete_user(self, client: AsyncClient):
        h = await _admin(client)
        await _register(client, "deleteme")
        r = await client.delete("/api/v1/admin/users/deleteme", headers=h)
        assert r.status_code == 200
        assert (await client.get("/api/v1/admin/users/deleteme", headers=h)).status_code == 404

    async def test_delete_own_account_rejected(self, client: AsyncClient):
        h = await _admin(client, "selfdelete")
        r = await client.delete("/api/v1/admin/users/selfdelete", headers=h)
        assert r.status_code == 400

    async def test_delete_nonexistent_user_returns_404(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.delete("/api/v1/admin/users/ghost_user", headers=h)
        assert r.status_code == 404

    async def test_user_management_requires_admin(self, client: AsyncClient):
        h = await _nonadmin(client, "nonadminuser2")
        assert (await client.get("/api/v1/admin/users", headers=h)).status_code == 403

    async def test_user_management_requires_auth(self, client: AsyncClient):
        assert (await client.get("/api/v1/admin/users")).status_code == 401


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Plugin listing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAdminPlugins:
    async def test_list_plugins_returns_200(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/plugins", headers=h)
        assert r.status_code == 200

    async def test_list_plugins_is_list(self, client: AsyncClient):
        h = await _admin(client)
        r = await client.get("/api/v1/admin/plugins", headers=h)
        assert isinstance(r.json(), list)

    async def test_plugin_entry_has_required_fields(self, client: AsyncClient):
        from app.services.plugins import BasePlugin, get_plugin_manager
        # Register a test plugin so the list is non-empty
        class _TestPlugin(BasePlugin):
            name = "test_admin_plugin"
            enabled = True
        mgr = get_plugin_manager()
        mgr.register(_TestPlugin())

        h = await _admin(client)
        r = await client.get("/api/v1/admin/plugins", headers=h)
        plugins = r.json()
        assert plugins
        entry = next(p for p in plugins if p["name"] == "test_admin_plugin")
        assert "name" in entry
        assert "enabled" in entry
        assert "plugin_class" in entry

    async def test_plugins_requires_admin(self, client: AsyncClient):
        h = await _nonadmin(client, "nonadminplugin")
        r = await client.get("/api/v1/admin/plugins", headers=h)
        assert r.status_code == 403

    async def test_plugins_requires_auth(self, client: AsyncClient):
        r = await client.get("/api/v1/admin/plugins")
        assert r.status_code == 401
