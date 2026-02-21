#!/usr/bin/env python
# -----------------------------------------------------------------------------
"""
Phase 3 — DataForms Tests
==========================
  - Search: full-text, topic-name, content, web-scoped
  - DataForms: schema CRUD, topic form assignment, field values
  - Admin management: make-admin, revoke-admin endpoints
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
# 1. Search
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSearch:
    async def _setup(self, client):
        h = await _admin_headers(client, "srchuser", web="SearchWeb")
        await _create_topic(client, h, "SearchWeb", "AlphaDoc",
                            "The quick brown fox jumps over the lazy dog")
        await _create_topic(client, h, "SearchWeb", "BetaDoc",
                            "Python asyncio and SQLAlchemy are great tools")
        return h

    async def test_search_by_content(self, client: AsyncClient):
        await self._setup(client)
        r = await client.get("/api/v1/search?q=asyncio")
        assert r.status_code == 200
        assert any(res["topic"] == "BetaDoc" for res in r.json())

    async def test_search_by_topic_name(self, client: AsyncClient):
        await self._setup(client)
        r = await client.get("/api/v1/search?q=Alpha&scope=topic")
        assert r.status_code == 200
        assert any(res["topic"] == "AlphaDoc" for res in r.json())

    async def test_search_scope_content_excludes_name_only(self, client: AsyncClient):
        await self._setup(client)
        r = await client.get("/api/v1/search?q=Alpha&scope=content")
        assert r.status_code == 200
        # "Alpha" is only in the topic name, not the content body
        assert not any(res["topic"] == "AlphaDoc" for res in r.json())

    async def test_search_web_scoped(self, client: AsyncClient):
        h  = await _admin_headers(client, "srchuser",  web="SearchWeb")
        h2 = await _admin_headers(client, "srchuser2", web="OtherWeb")
        await _create_topic(client, h,  "SearchWeb", "UniqueA", "foxtrot here")
        await _create_topic(client, h2, "OtherWeb",  "UniqueB", "foxtrot here")
        r = await client.get("/api/v1/search?q=foxtrot&web=SearchWeb")
        assert r.status_code == 200
        results = r.json()
        assert all(res["web"] == "SearchWeb" for res in results)
        assert any(res["topic"] == "UniqueA" for res in results)
        assert not any(res["topic"] == "UniqueB" for res in results)

    async def test_search_no_results(self, client: AsyncClient):
        await self._setup(client)
        r = await client.get("/api/v1/search?q=xyzzy_no_match_ever")
        assert r.status_code == 200
        assert r.json() == []

    async def test_search_empty_query_rejected(self, client: AsyncClient):
        r = await client.get("/api/v1/search?q=")
        assert r.status_code == 422

    async def test_search_result_has_excerpt(self, client: AsyncClient):
        await self._setup(client)
        r = await client.get("/api/v1/search?q=asyncio")
        assert r.status_code == 200
        results = r.json()
        assert results
        assert "asyncio" in results[0]["excerpt"].lower()

    async def test_search_limit(self, client: AsyncClient):
        h = await _admin_headers(client, "srchuser", web="SearchWeb")
        for i in range(5):
            await _create_topic(client, h, "SearchWeb", f"LimitTopic{i}",
                                "common keyword everywhere")
        r = await client.get("/api/v1/search?q=common&limit=3")
        assert r.status_code == 200
        assert len(r.json()) <= 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. DataForms
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SCHEMA = {
    "name": "BugReport",
    "description": "Bug tracking form",
    "fields": [
        {"name": "severity", "label": "Severity", "field_type": "select",
         "options": "low,medium,high", "is_required": True},
        {"name": "component", "label": "Component", "field_type": "text",
         "is_required": False},
    ],
}


class TestDataForms:
    async def _setup(self, client):
        h = await _admin_headers(client, "formuser", web="FormWeb")
        await _create_topic(client, h, "FormWeb", "FormTopic", "content")
        return h

    async def test_create_schema(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.post("/api/v1/forms", json=_SCHEMA, headers=h)
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "BugReport"
        assert len(body["fields"]) == 2

    async def test_list_schemas(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/forms", json=_SCHEMA, headers=h)
        r = await client.get("/api/v1/forms", headers=h)
        assert r.status_code == 200
        assert any(s["name"] == "BugReport" for s in r.json())

    async def test_get_schema_by_id(self, client: AsyncClient):
        h = await self._setup(client)
        sid = (await client.post("/api/v1/forms", json=_SCHEMA, headers=h)).json()["id"]
        r = await client.get(f"/api/v1/forms/{sid}", headers=h)
        assert r.status_code == 200
        assert r.json()["name"] == "BugReport"

    async def test_get_schema_not_found(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.get("/api/v1/forms/nonexistent-id", headers=h)
        assert r.status_code == 404

    async def test_update_schema_description(self, client: AsyncClient):
        h = await self._setup(client)
        sid = (await client.post("/api/v1/forms", json=_SCHEMA, headers=h)).json()["id"]
        r = await client.put(f"/api/v1/forms/{sid}",
                             json={"description": "Updated"}, headers=h)
        assert r.status_code == 200
        assert r.json()["description"] == "Updated"

    async def test_update_schema_replaces_fields(self, client: AsyncClient):
        h = await self._setup(client)
        sid = (await client.post("/api/v1/forms", json=_SCHEMA, headers=h)).json()["id"]
        r = await client.put(f"/api/v1/forms/{sid}", json={
            "fields": [{"name": "priority", "label": "Priority", "field_type": "text"}]
        }, headers=h)
        assert r.status_code == 200
        fields = r.json()["fields"]
        assert len(fields) == 1
        assert fields[0]["name"] == "priority"

    async def test_delete_schema(self, client: AsyncClient):
        h = await self._setup(client)
        sid = (await client.post("/api/v1/forms", json=_SCHEMA, headers=h)).json()["id"]
        assert (await client.delete(f"/api/v1/forms/{sid}", headers=h)).status_code == 200
        assert (await client.get(f"/api/v1/forms/{sid}", headers=h)).status_code == 404

    async def test_duplicate_schema_rejected(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/forms", json=_SCHEMA, headers=h)
        r = await client.post("/api/v1/forms", json=_SCHEMA, headers=h)
        assert r.status_code == 409

    async def test_assign_and_get_topic_form(self, client: AsyncClient):
        h = await self._setup(client)
        sid = (await client.post("/api/v1/forms", json=_SCHEMA, headers=h)).json()["id"]
        r = await client.put("/api/v1/webs/FormWeb/topics/FormTopic/form",
                             json={"schema_id": sid, "values": {"severity": "high"}},
                             headers=h)
        assert r.status_code == 200
        r2 = await client.get("/api/v1/webs/FormWeb/topics/FormTopic/form", headers=h)
        assert r2.status_code == 200
        body = r2.json()
        assert body["schema"]["name"] == "BugReport"
        assert body["values"]["severity"] == "high"

    async def test_get_topic_form_no_schema(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.get("/api/v1/webs/FormWeb/topics/FormTopic/form", headers=h)
        assert r.status_code == 200
        assert r.json()["schema"] is None

    async def test_remove_topic_form(self, client: AsyncClient):
        h = await self._setup(client)
        sid = (await client.post("/api/v1/forms", json=_SCHEMA, headers=h)).json()["id"]
        await client.put("/api/v1/webs/FormWeb/topics/FormTopic/form",
                         json={"schema_id": sid}, headers=h)
        assert (await client.delete(
            "/api/v1/webs/FormWeb/topics/FormTopic/form", headers=h
        )).status_code == 200
        assert (await client.get(
            "/api/v1/webs/FormWeb/topics/FormTopic/form", headers=h
        )).json()["schema"] is None

    async def test_forms_require_auth(self, client: AsyncClient):
        r = await client.get("/api/v1/forms")
        assert r.status_code == 401


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Admin management endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAdminManagement:
    async def _setup(self, client):
        h = await _admin_headers(client, "superadmin")
        await client.post("/api/v1/auth/register", json={
            "username": "regularjoe", "email": "joe@example.com",
            "password": "password123",
        })
        return h

    async def test_make_admin(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.patch("/api/v1/auth/users/regularjoe/make-admin", headers=h)
        assert r.status_code == 200
        assert r.json()["is_admin"] is True

    async def test_revoke_admin(self, client: AsyncClient):
        h = await self._setup(client)
        await client.patch("/api/v1/auth/users/regularjoe/make-admin", headers=h)
        r = await client.patch("/api/v1/auth/users/regularjoe/revoke-admin", headers=h)
        assert r.status_code == 200
        assert r.json()["is_admin"] is False

    async def test_make_admin_requires_admin_caller(self, client: AsyncClient):
        await self._setup(client)
        r = await client.post("/api/v1/auth/token",
                              data={"username": "regularjoe", "password": "password123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r2 = await client.patch("/api/v1/auth/users/superadmin/make-admin", headers=h)
        assert r2.status_code == 403

    async def test_make_admin_unknown_user_returns_404(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.patch("/api/v1/auth/users/nobody/make-admin", headers=h)
        assert r.status_code == 404

    async def test_revoke_admin_requires_admin_caller(self, client: AsyncClient):
        await self._setup(client)
        r = await client.post("/api/v1/auth/token",
                              data={"username": "regularjoe", "password": "password123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r2 = await client.patch("/api/v1/auth/users/superadmin/revoke-admin", headers=h)
        assert r2.status_code == 403
