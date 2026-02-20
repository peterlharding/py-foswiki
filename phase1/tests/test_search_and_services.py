#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""Tests for search endpoint and service-layer unit tests."""

from __future__ import annotations
import pytest
from httpx import AsyncClient
from tests.conftest import auth_headers


@pytest.mark.asyncio
class TestSearch:
    async def _populate(self, client):
        headers = await auth_headers(client, "searchuser")
        await client.post("/api/v1/webs", json={"name": "SearchWeb"}, headers=headers)
        for name, content in [
            ("PythonDev", "Python is a programming language used for web development"),
            ("JavaDev", "Java is used for enterprise backend development"),
            ("WebDesign", "CSS and HTML for web design and frontend"),
        ]:
            await client.post("/api/v1/webs/SearchWeb/topics", json={
                "name": name, "content": content
            }, headers=headers)
        return headers

    async def test_search_all(self, client: AsyncClient):
        await self._populate(client)
        resp = await client.get("/api/v1/search?q=development")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 2
        topics = [r["topic"] for r in results]
        assert "PythonDev" in topics
        assert "JavaDev" in topics

    async def test_search_content_only(self, client: AsyncClient):
        await self._populate(client)
        resp = await client.get("/api/v1/search?q=CSS&scope=content")
        assert resp.status_code == 200
        topics = [r["topic"] for r in resp.json()]
        assert "WebDesign" in topics

    async def test_search_topic_name_only(self, client: AsyncClient):
        await self._populate(client)
        resp = await client.get("/api/v1/search?q=Python&scope=topic")
        assert resp.status_code == 200
        topics = [r["topic"] for r in resp.json()]
        assert "PythonDev" in topics

    async def test_search_with_web_filter(self, client: AsyncClient):
        await self._populate(client)
        resp = await client.get("/api/v1/search?q=development&web=SearchWeb")
        assert resp.status_code == 200
        for r in resp.json():
            assert r["web"] == "SearchWeb"

    async def test_search_no_results(self, client: AsyncClient):
        await self._populate(client)
        resp = await client.get("/api/v1/search?q=zxqwerty12345")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_search_requires_query(self, client: AsyncClient):
        resp = await client.get("/api/v1/search")
        assert resp.status_code == 422

    async def test_search_excerpt_contains_query(self, client: AsyncClient):
        await self._populate(client)
        resp = await client.get("/api/v1/search?q=Python")
        assert resp.status_code == 200
        results = [r for r in resp.json() if r["topic"] == "PythonDev"]
        assert results
        assert "Python" in results[0]["excerpt"]

    async def test_search_limit(self, client: AsyncClient):
        await self._populate(client)
        resp = await client.get("/api/v1/search?q=dev&limit=1")
        assert resp.status_code == 200
        assert len(resp.json()) <= 1


@pytest.mark.asyncio
class TestServiceLayer:
    """Direct service function tests (not via HTTP)."""

    async def _setup_web_and_topic(self, db):
        from app.services.web_service import create_web
        from app.services.topic_service import create_topic
        from app.schemas import WebCreate, TopicCreate

        web = await create_web(db, WebCreate(name="SvcWeb"))
        await db.commit()

        topic = await create_topic(db, "SvcWeb", TopicCreate(
            name="SvcTopic",
            content="Initial content",
            comment="v1",
        ))
        await db.commit()
        return web, topic

    async def test_create_and_fetch_topic(self, db):
        from app.services.topic_service import get_topic

        await self._setup_web_and_topic(db)
        topic = await get_topic(db, "SvcWeb", "SvcTopic")
        assert topic.content == "Initial content"
        assert topic.current_version == 1

    async def test_version_increments(self, db):
        from app.services.topic_service import get_topic, save_topic
        from app.schemas import TopicSave

        await self._setup_web_and_topic(db)

        await save_topic(db, "SvcWeb", "SvcTopic", TopicSave(content="v2", comment="second"))
        await db.commit()
        await save_topic(db, "SvcWeb", "SvcTopic", TopicSave(content="v3", comment="third"))
        await db.commit()

        topic = await get_topic(db, "SvcWeb", "SvcTopic")
        assert topic.current_version == 3
        assert topic.content == "v3"

    async def test_history_count(self, db):
        from app.services.topic_service import get_history, save_topic
        from app.schemas import TopicSave

        await self._setup_web_and_topic(db)
        await save_topic(db, "SvcWeb", "SvcTopic", TopicSave(content="v2"))
        await db.commit()

        history = await get_history(db, "SvcWeb", "SvcTopic")
        assert len(history) == 2

    async def test_diff_content(self, db):
        from app.services.topic_service import diff_versions, save_topic
        from app.schemas import TopicSave

        await self._setup_web_and_topic(db)
        await save_topic(db, "SvcWeb", "SvcTopic", TopicSave(content="Modified content"))
        await db.commit()

        diff = await diff_versions(db, "SvcWeb", "SvcTopic", 1, 2)
        assert "-Initial content" in diff.unified_diff
        assert "+Modified content" in diff.unified_diff

    async def test_delete_removes_versions(self, db):
        from app.services.topic_service import delete_topic, get_topic, TopicNotFound

        await self._setup_web_and_topic(db)
        await delete_topic(db, "SvcWeb", "SvcTopic")
        await db.commit()

        with pytest.raises(TopicNotFound):
            await get_topic(db, "SvcWeb", "SvcTopic")

    async def test_meta_update(self, db):
        from app.services.topic_service import get_topic, save_topic
        from app.schemas import TopicSave

        await self._setup_web_and_topic(db)
        await save_topic(db, "SvcWeb", "SvcTopic", TopicSave(
            content="v2",
            meta={"Status": "Draft", "Owner": "Alice"},
        ))
        await db.commit()

        topic = await get_topic(db, "SvcWeb", "SvcTopic")
        assert topic.meta["Status"] == "Draft"
        assert topic.meta["Owner"] == "Alice"




