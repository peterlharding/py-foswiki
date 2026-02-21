#!/usr/bin/env python
# -----------------------------------------------------------------------------
"""
Feeds router
============
Provides RSS 2.0 and Atom 1.0 feeds for recent topic changes.

GET /api/v1/feeds/rss              — global RSS feed (all webs)
GET /api/v1/feeds/atom             — global Atom feed (all webs)
GET /api/v1/webs/{web}/feeds/rss   — per-web RSS feed
GET /api/v1/webs/{web}/feeds/atom  — per-web Atom feed

Query parameters (all endpoints):
  limit  int  Max items to return (default 20, max 100)
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.models import Topic, TopicVersion, Web


# -----------------------------------------------------------------------------

router = APIRouter(tags=["feeds"])

_RSS_CT  = "application/rss+xml; charset=utf-8"
_ATOM_CT = "application/atom+xml; charset=utf-8"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow_str() -> str:
    return datetime.now(tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _rfc822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt, usegmt=True)


async def _recent_versions(
    db: AsyncSession,
    web_name: Optional[str],
    limit: int,
) -> list[TopicVersion]:
    """Return the most-recent TopicVersion rows, optionally filtered by web."""
    stmt = (
        select(TopicVersion)
        .join(TopicVersion.topic)
        .join(Topic.web)
        .options(
            selectinload(TopicVersion.topic).selectinload(Topic.web),
            selectinload(TopicVersion.author),
        )
        .order_by(desc(TopicVersion.created_at))
        .limit(limit)
    )
    if web_name:
        stmt = stmt.where(Web.name == web_name)

    result = await db.execute(stmt)
    return list(result.scalars().all())


def _topic_url(base_url: str, web: str, topic: str) -> str:
    return f"{base_url}/api/v1/webs/{web}/topics/{topic}"


# ── RSS builder ───────────────────────────────────────────────────────────────

def _build_rss(
    versions: list[TopicVersion],
    base_url: str,
    site_name: str,
    feed_url: str,
    title: str,
    description: str,
) -> bytes:
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, "lastBuildDate").text = _utcnow_str()
    ET.SubElement(channel, "generator").text = f"{site_name} RSS"

    atom_link = ET.SubElement(channel, "atom:link")
    atom_link.set("href", feed_url)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    for ver in versions:
        topic = ver.topic
        web   = topic.web
        url   = _topic_url(base_url, web.name, topic.name)

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text    = f"{web.name}/{topic.name}"
        ET.SubElement(item, "link").text     = url
        ET.SubElement(item, "guid").text     = f"{url}?version={ver.version}"
        ET.SubElement(item, "pubDate").text  = _rfc822(ver.created_at)
        if ver.comment:
            ET.SubElement(item, "description").text = ver.comment
        if ver.author:
            ET.SubElement(item, "author").text = ver.author.display_name or ver.author.username

    return ET.tostring(rss, encoding="unicode", xml_declaration=False).encode()


# ── Atom builder ──────────────────────────────────────────────────────────────

def _build_atom(
    versions: list[TopicVersion],
    base_url: str,
    site_name: str,
    feed_url: str,
    title: str,
) -> bytes:
    ATOM = "http://www.w3.org/2005/Atom"

    feed = ET.Element(f"{{{ATOM}}}feed")
    ET.SubElement(feed, f"{{{ATOM}}}title").text = title
    ET.SubElement(feed, f"{{{ATOM}}}id").text    = feed_url
    ET.SubElement(feed, f"{{{ATOM}}}updated").text = _iso(datetime.now(tz=timezone.utc))
    ET.SubElement(feed, f"{{{ATOM}}}generator").text = site_name

    link_self = ET.SubElement(feed, f"{{{ATOM}}}link")
    link_self.set("rel", "self")
    link_self.set("href", feed_url)

    link_alt = ET.SubElement(feed, f"{{{ATOM}}}link")
    link_alt.set("rel", "alternate")
    link_alt.set("href", base_url)

    for ver in versions:
        topic = ver.topic
        web   = topic.web
        url   = _topic_url(base_url, web.name, topic.name)
        entry_id = f"{url}?version={ver.version}"

        entry = ET.SubElement(feed, f"{{{ATOM}}}entry")
        ET.SubElement(entry, f"{{{ATOM}}}title").text   = f"{web.name}/{topic.name}"
        ET.SubElement(entry, f"{{{ATOM}}}id").text      = entry_id
        ET.SubElement(entry, f"{{{ATOM}}}updated").text = _iso(ver.created_at)

        link_e = ET.SubElement(entry, f"{{{ATOM}}}link")
        link_e.set("rel", "alternate")
        link_e.set("href", url)

        if ver.author:
            author_el = ET.SubElement(entry, f"{{{ATOM}}}author")
            ET.SubElement(author_el, f"{{{ATOM}}}name").text = (
                ver.author.display_name or ver.author.username
            )

        if ver.comment:
            ET.SubElement(entry, f"{{{ATOM}}}summary").text = ver.comment

    ET.register_namespace("", ATOM)
    return ET.tostring(feed, encoding="unicode", xml_declaration=False).encode()


# ── Global feeds ──────────────────────────────────────────────────────────────

@router.get("/feeds/rss", summary="Global RSS feed")
async def global_rss(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    versions = await _recent_versions(db, web_name=None, limit=limit)
    feed_url = f"{settings.base_url}/api/v1/feeds/rss"
    body = _build_rss(
        versions,
        base_url=settings.base_url,
        site_name=settings.site_name,
        feed_url=feed_url,
        title=f"{settings.site_name} — Recent Changes",
        description=f"Recent topic changes across all webs on {settings.site_name}",
    )
    return Response(content=b'<?xml version="1.0" encoding="utf-8"?>\n' + body,
                    media_type=_RSS_CT)


@router.get("/feeds/atom", summary="Global Atom feed")
async def global_atom(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    versions = await _recent_versions(db, web_name=None, limit=limit)
    feed_url = f"{settings.base_url}/api/v1/feeds/atom"
    body = _build_atom(
        versions,
        base_url=settings.base_url,
        site_name=settings.site_name,
        feed_url=feed_url,
        title=f"{settings.site_name} — Recent Changes",
    )
    return Response(content=b'<?xml version="1.0" encoding="utf-8"?>\n' + body,
                    media_type=_ATOM_CT)


# ── Per-web feeds ─────────────────────────────────────────────────────────────

@router.get("/webs/{web_name}/feeds/rss", summary="Per-web RSS feed")
async def web_rss(
    web_name: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    versions = await _recent_versions(db, web_name=web_name, limit=limit)
    feed_url = f"{settings.base_url}/api/v1/webs/{web_name}/feeds/rss"
    body = _build_rss(
        versions,
        base_url=settings.base_url,
        site_name=settings.site_name,
        feed_url=feed_url,
        title=f"{settings.site_name} — {web_name} Recent Changes",
        description=f"Recent topic changes in the {web_name} web on {settings.site_name}",
    )
    return Response(content=b'<?xml version="1.0" encoding="utf-8"?>\n' + body,
                    media_type=_RSS_CT)


@router.get("/webs/{web_name}/feeds/atom", summary="Per-web Atom feed")
async def web_atom(
    web_name: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    versions = await _recent_versions(db, web_name=web_name, limit=limit)
    feed_url = f"{settings.base_url}/api/v1/webs/{web_name}/feeds/atom"
    body = _build_atom(
        versions,
        base_url=settings.base_url,
        site_name=settings.site_name,
        feed_url=feed_url,
        title=f"{settings.site_name} — {web_name} Recent Changes",
    )
    return Response(content=b'<?xml version="1.0" encoding="utf-8"?>\n' + body,
                    media_type=_ATOM_CT)
