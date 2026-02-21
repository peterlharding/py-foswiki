#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Phase 1 Integration Tests
=========================
Full API layer tests using AsyncClient + SQLite.

Coverage:
  - Auth: register, login, refresh, me
  - Users: duplicate handling, wrong password
  - Webs: CRUD, topic count
  - Topics: create, read, update, rename, delete, history, diff, raw
  - Topic versioning: append-only, multiple saves
  - Topic metadata: DataForms fields
  - Attachments: upload, list, download, delete
  - ACL: set and retrieve per-web and per-topic
  - Rendering integration: macros in topic content
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import io
import pytest
import pytest_asyncio
from httpx import AsyncClient


# -----------------------------------------------------------------------------

from tests.conftest import create_user_and_token


# -----------------------------------------------------------------------------

pytestmark = pytest.mark.asyncio


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Auth
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAuth:
    async def test_register_success(self, client: AsyncClient):
        r = await client.post("/api/v1/auth/register", json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "securepass1",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["username"] == "alice"
        assert data["wiki_name"] == "Alice"
        assert "password" not in data
        assert "password_hash" not in data

    async def test_register_duplicate_username(self, client: AsyncClient):
        payload = {"username": "bob", "email": "bob@example.com", "password": "pass1234"}
        await client.post("/api/v1/auth/register", json=payload)
        r = await client.post("/api/v1/auth/register", json=payload)
        assert r.status_code == 409

    async def test_register_duplicate_email(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={"username": "user1", "email": "shared@example.com", "password": "pass1234"})
        r = await client.post("/api/v1/auth/register", json={"username": "user2", "email": "shared@example.com", "password": "pass1234"})
        assert r.status_code == 409

    async def test_register_reserved_username(self, client: AsyncClient):
        r = await client.post("/api/v1/auth/register", json={"username": "admin", "email": "a@x.com", "password": "pass1234"})
        assert r.status_code == 422

    async def test_login_success(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={"username": "charlie", "email": "charlie@x.com", "password": "mypassword1"})
        r = await client.post("/api/v1/auth/token", data={"username": "charlie", "password": "mypassword1"})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={"username": "dave", "email": "dave@x.com", "password": "rightpass1"})
        r = await client.post("/api/v1/auth/token", data={"username": "dave", "password": "wrongpass1"})
        assert r.status_code == 401

    async def test_refresh_token(self, client: AsyncClient):
        _user, token = await create_user_and_token(client, "evan")
        r1 = await client.post("/api/v1/auth/token", data={"username": "evan", "password": "password123"})
        refresh_token = r1.json()["refresh_token"]
        r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert r2.status_code == 200
        assert "access_token" in r2.json()

    async def test_me_endpoint(self, client: AsyncClient):
        _user, token = await create_user_and_token(client, "faye")
        r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["username"] == "faye"

    async def test_me_no_token(self, client: AsyncClient):
        r = await client.get("/api/v1/auth/me")
        assert r.status_code == 401

    async def test_me_bad_token(self, client: AsyncClient):
        r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Webs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWebs:
    async def _auth(self, client):
        _u, t = await create_user_and_token(client, "webuser")
        return {"Authorization": f"Bearer {t}"}

    async def test_create_web(self, client: AsyncClient):
        headers = await self._auth(client)
        r = await client.post("/api/v1/webs", json={"name": "Main", "description": "Main web"}, headers=headers)
        assert r.status_code == 201
        assert r.json()["name"] == "Main"

    async def test_create_duplicate_web(self, client: AsyncClient):
        headers = await self._auth(client)
        await client.post("/api/v1/webs", json={"name": "Dev"}, headers=headers)
        r = await client.post("/api/v1/webs", json={"name": "Dev"}, headers=headers)
        assert r.status_code == 409

    async def test_list_webs(self, client: AsyncClient):
        headers = await self._auth(client)
        await client.post("/api/v1/webs", json={"name": "Alpha"}, headers=headers)
        await client.post("/api/v1/webs", json={"name": "Beta"}, headers=headers)
        r = await client.get("/api/v1/webs")
        assert r.status_code == 200
        names = [w["name"] for w in r.json()]
        assert "Alpha" in names
        assert "Beta" in names

    async def test_get_web(self, client: AsyncClient):
        headers = await self._auth(client)
        await client.post("/api/v1/webs", json={"name": "GetTest", "description": "Test desc"}, headers=headers)
        r = await client.get("/api/v1/webs/GetTest")
        assert r.status_code == 200
        assert r.json()["description"] == "Test desc"
        assert r.json()["topic_count"] == 0

    async def test_get_missing_web(self, client: AsyncClient):
        r = await client.get("/api/v1/webs/NoSuchWeb")
        assert r.status_code == 404

    async def test_update_web_description(self, client: AsyncClient):
        headers = await self._auth(client)
        await client.post("/api/v1/webs", json={"name": "UpdateMe"}, headers=headers)
        r = await client.patch("/api/v1/webs/UpdateMe", json={"description": "Updated!"}, headers=headers)
        assert r.status_code == 200
        assert r.json()["description"] == "Updated!"

    async def test_web_requires_auth_to_create(self, client: AsyncClient):
        r = await client.post("/api/v1/webs", json={"name": "Anon"})
        assert r.status_code == 401

    async def test_web_name_validation(self, client: AsyncClient):
        headers = await self._auth(client)
        r = await client.post("/api/v1/webs", json={"name": "has space"}, headers=headers)
        assert r.status_code == 422


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Topics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTopics:
    async def _setup(self, client):
        _u, t = await create_user_and_token(client, "topicuser")
        headers = {"Authorization": f"Bearer {t}"}
        await client.post("/api/v1/webs", json={"name": "TestWeb"}, headers=headers)
        return headers

    async def test_create_topic(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.post("/api/v1/webs/TestWeb/topics", json={
            "name": "WebHome",
            "content": "# Welcome\n\nThis is the home page.",
            "comment": "Initial",
        }, headers=h)
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "WebHome"
        assert body["version"] == 1
        assert body["rendered"] is not None
        assert "<h1" in body["rendered"]

    async def test_create_duplicate_topic(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "Dup", "content": "a"}, headers=h)
        r = await client.post("/api/v1/webs/TestWeb/topics", json={"name": "Dup", "content": "b"}, headers=h)
        assert r.status_code == 409

    async def test_get_topic(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "ReadMe", "content": "Hello **world**"}, headers=h)
        r = await client.get("/api/v1/webs/TestWeb/topics/ReadMe")
        assert r.status_code == 200
        body = r.json()
        assert body["content"] == "Hello **world**"
        assert "<strong>" in body["rendered"] or "<b>" in body["rendered"]

    async def test_get_raw_topic(self, client: AsyncClient):
        h = await self._setup(client)
        raw_content = "# Raw\n\nRaw content here."
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "RawTopic", "content": raw_content}, headers=h)
        r = await client.get("/api/v1/webs/TestWeb/topics/RawTopic/raw")
        assert r.status_code == 200
        assert r.text == raw_content

    async def test_get_missing_topic(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.get("/api/v1/webs/TestWeb/topics/NoSuchTopic")
        assert r.status_code == 404

    async def test_list_topics(self, client: AsyncClient):
        h = await self._setup(client)
        for name in ["Alpha", "Beta", "Gamma"]:
            await client.post("/api/v1/webs/TestWeb/topics", json={"name": name, "content": f"Content {name}"}, headers=h)
        r = await client.get("/api/v1/webs/TestWeb/topics")
        assert r.status_code == 200
        names = [t["name"] for t in r.json()]
        assert set(names) >= {"Alpha", "Beta", "Gamma"}

    async def test_list_topics_search(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "SearchTarget", "content": "x"}, headers=h)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "Unrelated", "content": "y"}, headers=h)
        r = await client.get("/api/v1/webs/TestWeb/topics?search=Search")
        assert r.status_code == 200
        names = [t["name"] for t in r.json()]
        assert "SearchTarget" in names
        assert "Unrelated" not in names

    async def test_update_topic_creates_version(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "VersionedPage", "content": "v1"}, headers=h)
        r2 = await client.put("/api/v1/webs/TestWeb/topics/VersionedPage", json={"content": "v2", "comment": "Edit 2"}, headers=h)
        assert r2.status_code == 200
        assert r2.json()["version"] == 2
        assert r2.json()["content"] == "v2"

    async def test_get_specific_version(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "MultiVer", "content": "version one"}, headers=h)
        await client.put("/api/v1/webs/TestWeb/topics/MultiVer", json={"content": "version two"}, headers=h)
        r = await client.get("/api/v1/webs/TestWeb/topics/MultiVer?version=1")
        assert r.status_code == 200
        assert r.json()["content"] == "version one"
        assert r.json()["version"] == 1

    async def test_topic_history(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "HistPage", "content": "v1"}, headers=h)
        await client.put("/api/v1/webs/TestWeb/topics/HistPage", json={"content": "v2"}, headers=h)
        await client.put("/api/v1/webs/TestWeb/topics/HistPage", json={"content": "v3"}, headers=h)
        r = await client.get("/api/v1/webs/TestWeb/topics/HistPage/history")
        assert r.status_code == 200
        versions = r.json()
        assert len(versions) == 3
        # Returned in descending order
        assert versions[0]["version"] == 3

    async def test_diff(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "DiffPage", "content": "line one\nline two\n"}, headers=h)
        await client.put("/api/v1/webs/TestWeb/topics/DiffPage", json={"content": "line one\nline THREE\n"}, headers=h)
        r = await client.get("/api/v1/webs/TestWeb/topics/DiffPage/diff/1/2")
        assert r.status_code == 200
        body = r.json()
        assert body["from_version"] == 1
        assert body["to_version"] == 2
        diff = body["diff"]
        types = {d["type"] for d in diff}
        assert "delete" in types or "insert" in types

    async def test_rename_topic(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "OldName", "content": "x"}, headers=h)
        r = await client.post("/api/v1/webs/TestWeb/topics/OldName/rename", json={"new_name": "NewName"}, headers=h)
        assert r.status_code == 200
        r2 = await client.get("/api/v1/webs/TestWeb/topics/NewName")
        assert r2.status_code == 200
        r3 = await client.get("/api/v1/webs/TestWeb/topics/OldName")
        assert r3.status_code == 404

    async def test_delete_topic(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "DeleteMe", "content": "bye"}, headers=h)
        r = await client.delete("/api/v1/webs/TestWeb/topics/DeleteMe", headers=h)
        assert r.status_code == 200
        r2 = await client.get("/api/v1/webs/TestWeb/topics/DeleteMe")
        assert r2.status_code == 404

    async def test_topic_with_metadata(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.post("/api/v1/webs/TestWeb/topics", json={
            "name": "MetaTopic",
            "content": "Some content",
            "meta": {"Status": "Draft", "Priority": "High"},
        }, headers=h)
        assert r.status_code == 201
        body = r.json()
        assert body["meta"]["Status"] == "Draft"
        assert body["meta"]["Priority"] == "High"

    async def test_update_metadata(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={
            "name": "MetaUpdate",
            "content": "Content",
            "meta": {"Status": "Draft"},
        }, headers=h)
        r = await client.put("/api/v1/webs/TestWeb/topics/MetaUpdate", json={
            "content": "Updated content",
            "meta": {"Status": "Published"},
        }, headers=h)
        assert r.status_code == 200
        assert r.json()["meta"]["Status"] == "Published"

    async def test_topic_name_validation(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.post("/api/v1/webs/TestWeb/topics", json={"name": "has space", "content": "x"}, headers=h)
        assert r.status_code == 422

    async def test_topic_requires_auth_to_create(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.post("/api/v1/webs/TestWeb/topics", json={"name": "Anon", "content": "x"})
        assert r.status_code == 401

    async def test_macro_rendered_in_topic(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.post("/api/v1/webs/TestWeb/topics", json={
            "name": "MacroPage",
            "content": "Web: %WEB%\nTopic: %TOPIC%",
        }, headers=h)
        assert r.status_code == 201
        rendered = r.json()["rendered"]
        assert "TestWeb" in rendered
        assert "MacroPage" in rendered

    async def test_web_topic_count_updates(self, client: AsyncClient):
        h = await self._setup(client)
        r_before = await client.get("/api/v1/webs/TestWeb")
        count_before = r_before.json()["topic_count"]
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "Counter1", "content": "x"}, headers=h)
        r_after = await client.get("/api/v1/webs/TestWeb")
        assert r_after.json()["topic_count"] == count_before + 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Attachments
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAttachments:
    async def _setup(self, client):
        _u, t = await create_user_and_token(client, "attuser")
        h = {"Authorization": f"Bearer {t}"}
        await client.post("/api/v1/webs", json={"name": "AttWeb"}, headers=h)
        await client.post("/api/v1/webs/AttWeb/topics", json={"name": "AttTopic", "content": "x"}, headers=h)
        return h

    async def test_upload_and_list(self, client: AsyncClient):
        h = await self._setup(client)
        content = b"Hello, attachment world!"
        r = await client.post(
            "/api/v1/webs/AttWeb/topics/AttTopic/attachments",
            files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
            data={"comment": "My text file"},
            headers=h,
        )
        assert r.status_code == 201
        body = r.json()
        assert body["filename"] == "test.txt"
        assert body["size_bytes"] == len(content)
        assert body["content_type"] == "text/plain"

        r2 = await client.get("/api/v1/webs/AttWeb/topics/AttTopic/attachments")
        assert r2.status_code == 200
        filenames = [a["filename"] for a in r2.json()]
        assert "test.txt" in filenames

    async def test_download_attachment(self, client: AsyncClient):
        h = await self._setup(client)
        content = b"download me"
        await client.post(
            "/api/v1/webs/AttWeb/topics/AttTopic/attachments",
            files={"file": ("dl.txt", io.BytesIO(content), "text/plain")},
            headers=h,
        )
        r = await client.get("/api/v1/webs/AttWeb/topics/AttTopic/attachments/dl.txt")
        assert r.status_code == 200
        assert r.content == content

    async def test_delete_attachment(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post(
            "/api/v1/webs/AttWeb/topics/AttTopic/attachments",
            files={"file": ("del.txt", io.BytesIO(b"bye"), "text/plain")},
            headers=h,
        )
        r = await client.delete("/api/v1/webs/AttWeb/topics/AttTopic/attachments/del.txt", headers=h)
        assert r.status_code == 200
        r2 = await client.get("/api/v1/webs/AttWeb/topics/AttTopic/attachments/del.txt")
        assert r2.status_code == 404

    async def test_overwrite_attachment(self, client: AsyncClient):
        h = await self._setup(client)
        await client.post(
            "/api/v1/webs/AttWeb/topics/AttTopic/attachments",
            files={"file": ("over.txt", io.BytesIO(b"v1"), "text/plain")},
            headers=h,
        )
        await client.post(
            "/api/v1/webs/AttWeb/topics/AttTopic/attachments",
            files={"file": ("over.txt", io.BytesIO(b"version2"), "text/plain")},
            headers=h,
        )
        r = await client.get("/api/v1/webs/AttWeb/topics/AttTopic/attachments/over.txt")
        assert r.content == b"version2"

    async def test_upload_requires_auth(self, client: AsyncClient):
        await self._setup(client)
        r = await client.post(
            "/api/v1/webs/AttWeb/topics/AttTopic/attachments",
            files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
        )
        assert r.status_code == 401

    async def test_filename_sanitisation(self, client: AsyncClient):
        h = await self._setup(client)
        r = await client.post(
            "/api/v1/webs/AttWeb/topics/AttTopic/attachments",
            files={"file": ("../../../etc/passwd", io.BytesIO(b"nope"), "text/plain")},
            headers=h,
        )
        assert r.status_code == 201
        # Path traversal component must be stripped
        assert ".." not in r.json()["filename"]
        assert "/" not in r.json()["filename"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. ACL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestACL:
    async def _setup_admin(self, client):
        """Create an admin user via the shared test session."""
        _u, token = await create_user_and_token(client, "aclAdmin", "adminpass1")
        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/api/v1/webs", json={"name": "AclWeb"}, headers=headers)
        await client.post("/api/v1/webs/AclWeb/topics", json={"name": "AclTopic", "content": "x"}, headers=headers)
        return headers

    async def test_set_and_get_web_acl(self, client: AsyncClient):
        h = await self._setup_admin(client)
        entries = [
            {"principal": "*",         "permission": "view", "allow": True},
            {"principal": "group:Dev", "permission": "edit", "allow": True},
        ]
        r = await client.put("/api/v1/webs/AclWeb/acl", json={"entries": entries}, headers=h)
        assert r.status_code == 200
        body = r.json()
        assert len(body["entries"]) == 2

        r2 = await client.get("/api/v1/webs/AclWeb/acl", headers=h)
        assert r2.status_code == 200
        returned = {(e["principal"], e["permission"]) for e in r2.json()["entries"]}
        assert ("*", "view") in returned
        assert ("group:Dev", "edit") in returned

    async def test_set_and_get_topic_acl(self, client: AsyncClient):
        h = await self._setup_admin(client)
        entries = [{"principal": "user:aclAdmin", "permission": "admin", "allow": True}]
        r = await client.put("/api/v1/webs/AclWeb/topics/AclTopic/acl", json={"entries": entries}, headers=h)
        assert r.status_code == 200

        r2 = await client.get("/api/v1/webs/AclWeb/topics/AclTopic/acl", headers=h)
        assert r2.status_code == 200
        assert r2.json()["resource_type"] == "topic"

    async def test_invalid_permission(self, client: AsyncClient):
        h = await self._setup_admin(client)
        r = await client.put("/api/v1/webs/AclWeb/acl", json={
            "entries": [{"principal": "*", "permission": "fly", "allow": True}]
        }, headers=h)
        assert r.status_code == 422


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. System
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSystem:
    async def test_health(self, client: AsyncClient):
        r = await client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# -----------------------------------------------------------------------------

