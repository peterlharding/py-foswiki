#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""Tests for Webs and Topics endpoints."""

from __future__ import annotations
import pytest
from httpx import AsyncClient
from tests.conftest import auth_headers


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Webs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.asyncio
class TestWebs:
    async def _headers(self, client):
        return await auth_headers(client, "webuser")

    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/webs")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_web(self, client: AsyncClient):
        headers = await self._headers(client)
        resp = await client.post("/api/v1/webs", json={"name": "Main", "description": "Main web"}, headers=headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Main"
        assert body["description"] == "Main web"

    async def test_list_after_create(self, client: AsyncClient):
        headers = await self._headers(client)
        await client.post("/api/v1/webs", json={"name": "Alpha"}, headers=headers)
        await client.post("/api/v1/webs", json={"name": "Beta"}, headers=headers)
        resp = await client.get("/api/v1/webs")
        assert resp.status_code == 200
        names = [w["name"] for w in resp.json()]
        assert "Alpha" in names
        assert "Beta" in names

    async def test_get_web(self, client: AsyncClient):
        headers = await self._headers(client)
        await client.post("/api/v1/webs", json={"name": "GetMe"}, headers=headers)
        resp = await client.get("/api/v1/webs/GetMe")
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetMe"

    async def test_get_web_not_found(self, client: AsyncClient):
        resp = await client.get("/api/v1/webs/DoesNotExist")
        assert resp.status_code == 404

    async def test_create_web_duplicate(self, client: AsyncClient):
        headers = await self._headers(client)
        await client.post("/api/v1/webs", json={"name": "Dup"}, headers=headers)
        resp = await client.post("/api/v1/webs", json={"name": "Dup"}, headers=headers)
        assert resp.status_code == 409

    async def test_create_web_requires_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/webs", json={"name": "Unauth"})
        assert resp.status_code == 401

    async def test_update_web(self, client: AsyncClient):
        headers = await self._headers(client)
        await client.post("/api/v1/webs", json={"name": "UpdateMe", "description": "old"}, headers=headers)
        resp = await client.put("/api/v1/webs/UpdateMe", json={"description": "updated"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["description"] == "updated"

    async def test_invalid_web_name(self, client: AsyncClient):
        headers = await self._headers(client)
        resp = await client.post("/api/v1/webs", json={"name": "bad name!"}, headers=headers)
        assert resp.status_code == 422


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Topics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.asyncio
class TestTopics:
    async def _setup(self, client):
        """Create user + web, return auth headers."""
        headers = await auth_headers(client, "topicuser")
        await client.post("/api/v1/webs", json={"name": "TestWeb"}, headers=headers)
        return headers

    async def test_list_empty(self, client: AsyncClient):
        headers = await self._setup(client)
        resp = await client.get("/api/v1/webs/TestWeb/topics")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_topic(self, client: AsyncClient):
        headers = await self._setup(client)
        resp = await client.post("/api/v1/webs/TestWeb/topics", json={
            "name": "WebHome",
            "content": "# Welcome\n\nThis is the home page.",
            "comment": "Initial",
        }, headers=headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "WebHome"
        assert body["current_version"] == 1
        assert "Welcome" in body["content"]
        assert body["web_name"] == "TestWeb"

    async def test_get_topic(self, client: AsyncClient):
        headers = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "MyTopic", "content": "Hello"}, headers=headers)
        resp = await client.get("/api/v1/webs/TestWeb/topics/MyTopic")
        assert resp.status_code == 200
        assert resp.json()["content"] == "Hello"

    async def test_get_topic_not_found(self, client: AsyncClient):
        headers = await self._setup(client)
        resp = await client.get("/api/v1/webs/TestWeb/topics/NeverCreated")
        assert resp.status_code == 404

    async def test_get_raw(self, client: AsyncClient):
        headers = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "RawTopic", "content": "raw content"}, headers=headers)
        resp = await client.get("/api/v1/webs/TestWeb/topics/RawTopic/raw")
        assert resp.status_code == 200
        assert resp.json()["content"] == "raw content"

    async def test_create_duplicate_topic(self, client: AsyncClient):
        headers = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "DupTopic"}, headers=headers)
        resp = await client.post("/api/v1/webs/TestWeb/topics", json={"name": "DupTopic"}, headers=headers)
        assert resp.status_code == 409

    async def test_save_new_version(self, client: AsyncClient):
        headers = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "Versioned", "content": "v1"}, headers=headers)
        resp = await client.put("/api/v1/webs/TestWeb/topics/Versioned", json={
            "content": "v2 content",
            "comment": "Updated",
        }, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_version"] == 2
        assert body["content"] == "v2 content"

    async def test_save_requires_auth(self, client: AsyncClient):
        headers = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "AuthReq"}, headers=headers)
        resp = await client.put("/api/v1/webs/TestWeb/topics/AuthReq", json={"content": "x"})
        assert resp.status_code == 401

    async def test_list_topics(self, client: AsyncClient):
        headers = await self._setup(client)
        for name in ["TopicA", "TopicB", "TopicC"]:
            await client.post("/api/v1/webs/TestWeb/topics", json={"name": name, "content": name}, headers=headers)
        resp = await client.get("/api/v1/webs/TestWeb/topics")
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert set(names) == {"TopicA", "TopicB", "TopicC"}

    async def test_list_topics_search(self, client: AsyncClient):
        headers = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "FindMe"}, headers=headers)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "HideMe"}, headers=headers)
        resp = await client.get("/api/v1/webs/TestWeb/topics?search=Find")
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "FindMe" in names
        assert "HideMe" not in names

    async def test_delete_topic(self, client: AsyncClient):
        headers = await self._setup(client)
        await client.post("/api/v1/webs/TestWeb/topics", json={"name": "DeleteMe"}, headers=headers)
        resp = await client.delete("/api/v1/webs/TestWeb/topics/DeleteMe", headers=headers)
        assert resp.status_code == 204
        get_resp = await client.get("/api/v1/webs/TestWeb/topics/DeleteMe")
        assert get_resp.status_code == 404

    async def test_topic_with_meta(self, client: AsyncClient):
        headers = await self._setup(client)
        resp = await client.post("/api/v1/webs/TestWeb/topics", json={
            "name": "MetaTopic",
            "content": "content",
            "meta": {"Status": "Active", "Priority": "High"},
        }, headers=headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["meta"]["Status"] == "Active"
        assert body["meta"]["Priority"] == "High"

    async def test_create_topic_requires_auth(self, client: AsyncClient):
        headers = await self._setup(client)
        resp = await client.post("/api/v1/webs/TestWeb/topics", json={"name": "NoAuth", "content": "x"})
        assert resp.status_code == 401


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# History & Diff
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.asyncio
class TestHistory:
    async def _create_versioned_topic(self, client):
        headers = await auth_headers(client, "histuser")
        await client.post("/api/v1/webs", json={"name": "HistWeb"}, headers=headers)
        await client.post("/api/v1/webs/HistWeb/topics", json={
            "name": "HistTopic", "content": "Version one content", "comment": "First"
        }, headers=headers)
        await client.put("/api/v1/webs/HistWeb/topics/HistTopic", json={
            "content": "Version two content", "comment": "Second"
        }, headers=headers)
        await client.put("/api/v1/webs/HistWeb/topics/HistTopic", json={
            "content": "Version three content", "comment": "Third"
        }, headers=headers)
        return headers

    async def test_history_returns_all_versions(self, client: AsyncClient):
        await self._create_versioned_topic(client)
        resp = await client.get("/api/v1/webs/HistWeb/topics/HistTopic/history")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 3
        # Newest first
        assert history[0]["version"] == 3
        assert history[1]["version"] == 2
        assert history[2]["version"] == 1

    async def test_history_has_comments(self, client: AsyncClient):
        await self._create_versioned_topic(client)
        resp = await client.get("/api/v1/webs/HistWeb/topics/HistTopic/history")
        history = resp.json()
        comments = [h["comment"] for h in history]
        assert "Third" in comments
        assert "Second" in comments
        assert "First" in comments

    async def test_get_specific_version(self, client: AsyncClient):
        await self._create_versioned_topic(client)
        resp = await client.get("/api/v1/webs/HistWeb/topics/HistTopic/history/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == 1
        assert body["content"] == "Version one content"

    async def test_get_version_not_found(self, client: AsyncClient):
        await self._create_versioned_topic(client)
        resp = await client.get("/api/v1/webs/HistWeb/topics/HistTopic/history/99")
        assert resp.status_code == 404

    async def test_get_topic_by_version_query(self, client: AsyncClient):
        await self._create_versioned_topic(client)
        resp = await client.get("/api/v1/webs/HistWeb/topics/HistTopic?version=2")
        assert resp.status_code == 200
        assert resp.json()["content"] == "Version two content"
        assert resp.json()["current_version"] == 2

    async def test_diff_versions(self, client: AsyncClient):
        await self._create_versioned_topic(client)
        resp = await client.get("/api/v1/webs/HistWeb/topics/HistTopic/diff/1/3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["from_version"] == 1
        assert body["to_version"] == 3
        assert "---" in body["unified_diff"]
        assert "+++" in body["unified_diff"]
        assert "-Version one content" in body["unified_diff"]
        assert "+Version three content" in body["unified_diff"]

    async def test_diff_no_change(self, client: AsyncClient):
        await self._create_versioned_topic(client)
        resp = await client.get("/api/v1/webs/HistWeb/topics/HistTopic/diff/1/1")
        assert resp.status_code == 200
        # Diff of a version with itself should be empty
        assert resp.json()["unified_diff"] == ""



