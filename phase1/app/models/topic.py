#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Topic / TopicVersion models
===========================
Topic         — identity record (name, web, timestamps)
TopicVersion  — append-only version table (content, author, comment, timestamp)
TopicMeta     — key/value metadata attached to a topic (DataForm fields)

Fetching the current content means: join on MAX(version) for a topic_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("web_id", "name", name="uq_topic_web_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    web_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("webs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ── Relationships ───────────────────────────────────────────────────────
    web: Mapped["Web"] = relationship(back_populates="topics", lazy="raise")  # noqa: F821
    versions: Mapped[list["TopicVersion"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="TopicVersion.version",
        lazy="raise",
    )
    meta_fields: Mapped[list["TopicMeta"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    attachments: Mapped[list["Attachment"]] = relationship(  # noqa: F821
        back_populates="topic",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<Topic {self.name!r}>"


class TopicVersion(Base):
    __tablename__ = "topic_versions"
    __table_args__ = (UniqueConstraint("topic_id", "version", name="uq_topic_version"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    comment: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # ── Relationships ───────────────────────────────────────────────────────
    topic: Mapped["Topic"] = relationship(back_populates="versions", lazy="raise")
    author: Mapped[Optional["User"]] = relationship(  # noqa: F821
        back_populates="topic_versions", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<TopicVersion topic={self.topic_id} v={self.version}>"


class TopicMeta(Base):
    __tablename__ = "topic_meta"
    __table_args__ = (UniqueConstraint("topic_id", "key", name="uq_topic_meta_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")

    topic: Mapped["Topic"] = relationship(back_populates="meta_fields", lazy="raise")




