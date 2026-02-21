#!/usr/bin/env python
# -----------------------------------------------------------------------------
"""
Phase 5 — RSS / Atom Feed Tests
=================================
  - Global RSS and Atom feeds
  - Per-web RSS and Atom feeds
  - Correct Content-Type headers
  - Feed contains expected entries
  - limit parameter respected
  - Empty feed (no topics) returns valid XML
  - Unknown web returns empty feed (not 404)
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from httpx import AsyncClient

from tests.conftest import create_user_and_token

pytestmark = pytest.mark.asyncio

_ATOM_NS = "http://www.w3.org/2005/Atom"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _setup(client: AsyncClient, web: str = "FeedWeb") -> dict:
    _u, tok = await create_user_and_token(client, "feeduser", is_admin=True)
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post("/api/v1/webs", json={"name": web}, headers=h)
    assert r.status_code in (201, 409), r.text
    return h


async def _create_topic(client, headers, web, name, content="body text"):
    r = await client.post(
        f"/api/v1/webs/{web}/topics",
        json={"name": name, "content": content, "comment": f"create {name}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text


def _parse(xml_bytes: bytes) -> ET.Element:
    return ET.fromstring(xml_bytes)


def _rss_titles(root: ET.Element) -> list[str]:
    return [item.findtext("title") or "" for item in root.findall(".//item")]


def _atom_titles(root: ET.Element) -> list[str]:
    return [
        el.text or ""
        for el in root.findall(f"{{{_ATOM_NS}}}entry/{{{_ATOM_NS}}}title")
    ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RSS — global
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestGlobalRSS:
    async def test_returns_200(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/rss")
        assert r.status_code == 200

    async def test_content_type_is_rss(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/rss")
        assert "rss" in r.headers["content-type"]

    async def test_valid_xml(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/rss")
        root = _parse(r.content)
        assert root.tag == "rss"

    async def test_has_channel(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/rss")
        root = _parse(r.content)
        assert root.find("channel") is not None

    async def test_empty_feed_is_valid(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/rss")
        root = _parse(r.content)
        assert root.find(".//item") is None

    async def test_contains_topic_entry(self, client: AsyncClient):
        h = await _setup(client)
        await _create_topic(client, h, "FeedWeb", "RssGlobalTopic")
        r = await client.get("/api/v1/feeds/rss")
        titles = _rss_titles(_parse(r.content))
        assert any("RssGlobalTopic" in t for t in titles)

    async def test_entry_has_link(self, client: AsyncClient):
        h = await _setup(client)
        await _create_topic(client, h, "FeedWeb", "RssLinkTopic")
        r = await client.get("/api/v1/feeds/rss")
        root = _parse(r.content)
        links = [item.findtext("link") for item in root.findall(".//item")]
        assert any(links)

    async def test_entry_has_guid(self, client: AsyncClient):
        h = await _setup(client)
        await _create_topic(client, h, "FeedWeb", "RssGuidTopic")
        r = await client.get("/api/v1/feeds/rss")
        root = _parse(r.content)
        guids = [item.findtext("guid") for item in root.findall(".//item")]
        assert any(guids)

    async def test_entry_has_pubdate(self, client: AsyncClient):
        h = await _setup(client)
        await _create_topic(client, h, "FeedWeb", "RssDateTopic")
        r = await client.get("/api/v1/feeds/rss")
        root = _parse(r.content)
        dates = [item.findtext("pubDate") for item in root.findall(".//item")]
        assert any(dates)

    async def test_limit_parameter(self, client: AsyncClient):
        h = await _setup(client)
        for i in range(5):
            await _create_topic(client, h, "FeedWeb", f"RssLimit{i}")
        r = await client.get("/api/v1/feeds/rss?limit=3")
        root = _parse(r.content)
        assert len(root.findall(".//item")) <= 3

    async def test_limit_above_max_rejected(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/rss?limit=999")
        assert r.status_code == 422

    async def test_multiple_webs_all_appear(self, client: AsyncClient):
        h1 = await _setup(client, "FeedWeb")
        h2 = await _setup(client, "OtherFeedWeb")
        await _create_topic(client, h1, "FeedWeb",      "TopicAlpha")
        await _create_topic(client, h2, "OtherFeedWeb", "TopicBeta")
        r = await client.get("/api/v1/feeds/rss")
        titles = _rss_titles(_parse(r.content))
        assert any("TopicAlpha" in t for t in titles)
        assert any("TopicBeta"  in t for t in titles)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Atom — global
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestGlobalAtom:
    async def test_returns_200(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/atom")
        assert r.status_code == 200

    async def test_content_type_is_atom(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/atom")
        assert "atom" in r.headers["content-type"]

    async def test_valid_xml(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/atom")
        root = _parse(r.content)
        assert root.tag == f"{{{_ATOM_NS}}}feed"

    async def test_empty_feed_is_valid(self, client: AsyncClient):
        r = await client.get("/api/v1/feeds/atom")
        root = _parse(r.content)
        assert root.find(f"{{{_ATOM_NS}}}entry") is None

    async def test_contains_topic_entry(self, client: AsyncClient):
        h = await _setup(client)
        await _create_topic(client, h, "FeedWeb", "AtomGlobalTopic")
        r = await client.get("/api/v1/feeds/atom")
        titles = _atom_titles(_parse(r.content))
        assert any("AtomGlobalTopic" in t for t in titles)

    async def test_entry_has_id(self, client: AsyncClient):
        h = await _setup(client)
        await _create_topic(client, h, "FeedWeb", "AtomIdTopic")
        r = await client.get("/api/v1/feeds/atom")
        root = _parse(r.content)
        ids = [el.text for el in root.findall(f".//{{{_ATOM_NS}}}entry/{{{_ATOM_NS}}}id")]
        assert any(ids)

    async def test_entry_has_updated(self, client: AsyncClient):
        h = await _setup(client)
        await _create_topic(client, h, "FeedWeb", "AtomUpdatedTopic")
        r = await client.get("/api/v1/feeds/atom")
        root = _parse(r.content)
        updated = [el.text for el in root.findall(f".//{{{_ATOM_NS}}}entry/{{{_ATOM_NS}}}updated")]
        assert any(updated)

    async def test_limit_parameter(self, client: AsyncClient):
        h = await _setup(client)
        for i in range(5):
            await _create_topic(client, h, "FeedWeb", f"AtomLimit{i}")
        r = await client.get("/api/v1/feeds/atom?limit=2")
        root = _parse(r.content)
        assert len(root.findall(f"{{{_ATOM_NS}}}entry")) <= 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RSS — per-web
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWebRSS:
    async def test_returns_200(self, client: AsyncClient):
        await _setup(client)
        r = await client.get("/api/v1/webs/FeedWeb/feeds/rss")
        assert r.status_code == 200

    async def test_content_type_is_rss(self, client: AsyncClient):
        await _setup(client)
        r = await client.get("/api/v1/webs/FeedWeb/feeds/rss")
        assert "rss" in r.headers["content-type"]

    async def test_valid_xml(self, client: AsyncClient):
        await _setup(client)
        r = await client.get("/api/v1/webs/FeedWeb/feeds/rss")
        root = _parse(r.content)
        assert root.tag == "rss"

    async def test_only_contains_topics_from_web(self, client: AsyncClient):
        h1 = await _setup(client, "FeedWeb")
        h2 = await _setup(client, "OtherFeedWeb")
        await _create_topic(client, h1, "FeedWeb",      "WebOnlyTopic")
        await _create_topic(client, h2, "OtherFeedWeb", "OtherWebTopic")
        r = await client.get("/api/v1/webs/FeedWeb/feeds/rss")
        titles = _rss_titles(_parse(r.content))
        assert any("WebOnlyTopic"  in t for t in titles)
        assert not any("OtherWebTopic" in t for t in titles)

    async def test_unknown_web_returns_empty_feed(self, client: AsyncClient):
        r = await client.get("/api/v1/webs/NoSuchWeb/feeds/rss")
        assert r.status_code == 200
        root = _parse(r.content)
        assert root.find(".//item") is None

    async def test_limit_parameter(self, client: AsyncClient):
        h = await _setup(client)
        for i in range(5):
            await _create_topic(client, h, "FeedWeb", f"WebRssLimit{i}")
        r = await client.get("/api/v1/webs/FeedWeb/feeds/rss?limit=2")
        root = _parse(r.content)
        assert len(root.findall(".//item")) <= 2

    async def test_title_includes_web_name(self, client: AsyncClient):
        await _setup(client)
        r = await client.get("/api/v1/webs/FeedWeb/feeds/rss")
        root = _parse(r.content)
        title = root.findtext(".//channel/title") or ""
        assert "FeedWeb" in title


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Atom — per-web
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWebAtom:
    async def test_returns_200(self, client: AsyncClient):
        await _setup(client)
        r = await client.get("/api/v1/webs/FeedWeb/feeds/atom")
        assert r.status_code == 200

    async def test_content_type_is_atom(self, client: AsyncClient):
        await _setup(client)
        r = await client.get("/api/v1/webs/FeedWeb/feeds/atom")
        assert "atom" in r.headers["content-type"]

    async def test_valid_xml(self, client: AsyncClient):
        await _setup(client)
        r = await client.get("/api/v1/webs/FeedWeb/feeds/atom")
        root = _parse(r.content)
        assert root.tag == f"{{{_ATOM_NS}}}feed"

    async def test_only_contains_topics_from_web(self, client: AsyncClient):
        h1 = await _setup(client, "FeedWeb")
        h2 = await _setup(client, "OtherFeedWeb")
        await _create_topic(client, h1, "FeedWeb",      "AtomWebOnly")
        await _create_topic(client, h2, "OtherFeedWeb", "AtomOtherWeb")
        r = await client.get("/api/v1/webs/FeedWeb/feeds/atom")
        titles = _atom_titles(_parse(r.content))
        assert any("AtomWebOnly"  in t for t in titles)
        assert not any("AtomOtherWeb" in t for t in titles)

    async def test_unknown_web_returns_empty_feed(self, client: AsyncClient):
        r = await client.get("/api/v1/webs/NoSuchWeb/feeds/atom")
        assert r.status_code == 200
        root = _parse(r.content)
        assert root.find(f"{{{_ATOM_NS}}}entry") is None

    async def test_limit_parameter(self, client: AsyncClient):
        h = await _setup(client)
        for i in range(5):
            await _create_topic(client, h, "FeedWeb", f"WebAtomLimit{i}")
        r = await client.get("/api/v1/webs/FeedWeb/feeds/atom?limit=2")
        root = _parse(r.content)
        assert len(root.findall(f"{{{_ATOM_NS}}}entry")) <= 2

    async def test_title_includes_web_name(self, client: AsyncClient):
        await _setup(client)
        r = await client.get("/api/v1/webs/FeedWeb/feeds/atom")
        root = _parse(r.content)
        title_el = root.find(f"{{{_ATOM_NS}}}title")
        assert title_el is not None
        assert "FeedWeb" in (title_el.text or "")

    async def test_feed_has_self_link(self, client: AsyncClient):
        await _setup(client)
        r = await client.get("/api/v1/webs/FeedWeb/feeds/atom")
        root = _parse(r.content)
        links = root.findall(f"{{{_ATOM_NS}}}link")
        self_links = [l for l in links if l.get("rel") == "self"]
        assert self_links
