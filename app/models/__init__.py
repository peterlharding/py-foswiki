
"""
ORM Models — Phase 1 schema
============================

Tables
------
users           — accounts with hashed passwords and group membership
webs            — wiki namespaces (can be nested)
topics          — pages within a web
topic_versions  — append-only version history (one row per save)
topic_meta      — key/value structured metadata (DataForms lite)
attachments     — files uploaded to a topic
acl             — per-web / per-topic access control entries

All primary keys are UUIDs.  Timestamps stored in UTC.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, BigInteger,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# Helper so we can swap PG_UUID ↔ String depending on the engine
def _uuid_col(primary_key=False, nullable=False, **kw):
    """UUID column that works for both PostgreSQL and SQLite."""
    return mapped_column(
        String(36),
        primary_key=primary_key,
        nullable=nullable,
        default=lambda: str(uuid.uuid4()),
        **kw,
    )


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# users
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class User(Base):
    __tablename__ = "users"

    id:           Mapped[str]  = _uuid_col(primary_key=True)
    username:     Mapped[str]  = mapped_column(String(64),  unique=True, nullable=False, index=True)
    email:        Mapped[str]  = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str]  = mapped_column(String(128), nullable=False, default="")
    wiki_name:    Mapped[str]  = mapped_column(String(128), nullable=False, default="")
    password_hash:Mapped[str]  = mapped_column(String(255), nullable=False)
    is_active:    Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin:     Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Comma-separated group names (simple; use a junction table for scale)
    groups:       Mapped[str]  = mapped_column(Text, default="", nullable=False)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    topic_versions: Mapped[list["TopicVersion"]] = relationship(back_populates="author")
    attachments:    Mapped[list["Attachment"]]   = relationship(back_populates="uploaded_by_user")

    def groups_list(self) -> list[str]:
        return [g.strip() for g in self.groups.split(",") if g.strip()]

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "username":     self.username,
            "email":        self.email,
            "display_name": self.display_name,
            "wiki_name":    self.wiki_name,
            "is_admin":     self.is_admin,
            "groups":       self.groups_list(),
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# webs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Web(Base):
    __tablename__ = "webs"

    id:          Mapped[str]            = _uuid_col(primary_key=True)
    name:        Mapped[str]            = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str]            = mapped_column(Text, default="", nullable=False)
    parent_id:   Mapped[str | None]     = mapped_column(String(36), ForeignKey("webs.id"), nullable=True)
    created_at:  Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    parent:   Mapped["Web | None"]  = relationship("Web", remote_side="Web.id", back_populates="children")
    children: Mapped[list["Web"]]   = relationship("Web", back_populates="parent")
    topics:   Mapped[list["Topic"]] = relationship(back_populates="web", cascade="all, delete-orphan")
    acl:      Mapped[list["ACL"]]   = relationship(
        back_populates="web",
        primaryjoin="and_(ACL.resource_type=='web', foreign(ACL.resource_id)==Web.id)",
        viewonly=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# topics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("web_id", "name", name="uq_topics_web_name"),
    )

    id:             Mapped[str]        = _uuid_col(primary_key=True)
    web_id:         Mapped[str]        = mapped_column(String(36), ForeignKey("webs.id", ondelete="CASCADE"), nullable=False, index=True)
    name:           Mapped[str]        = mapped_column(String(256), nullable=False, index=True)
    created_by:     Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at:     Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=_utcnow)
    form_schema_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("form_schemas.id", ondelete="SET NULL"), nullable=True, index=True)

    # Relationships
    web:         Mapped["Web"]                 = relationship(back_populates="topics")
    creator:     Mapped["User | None"]         = relationship(foreign_keys=[created_by])
    versions:    Mapped[list["TopicVersion"]]  = relationship(back_populates="topic", cascade="all, delete-orphan", order_by="TopicVersion.version")
    meta:        Mapped[list["TopicMeta"]]     = relationship(back_populates="topic", cascade="all, delete-orphan")
    attachments: Mapped[list["Attachment"]]    = relationship(back_populates="topic", cascade="all, delete-orphan")
    form_schema: Mapped["FormSchema | None"]   = relationship(back_populates="topics", foreign_keys=[form_schema_id])

    @property
    def latest_version(self) -> "TopicVersion | None":
        return self.versions[-1] if self.versions else None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# topic_versions  (append-only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TopicVersion(Base):
    __tablename__ = "topic_versions"
    __table_args__ = (
        UniqueConstraint("topic_id", "version", name="uq_topic_versions_topic_ver"),
        Index("ix_topic_versions_topic_latest", "topic_id", "version"),
    )

    id:        Mapped[str]  = _uuid_col(primary_key=True)
    topic_id:  Mapped[str]  = mapped_column(String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    version:   Mapped[int]  = mapped_column(Integer, nullable=False)
    content:   Mapped[str]  = mapped_column(Text, nullable=False, default="")
    # Cached rendered HTML (invalidated on save)
    rendered:  Mapped[str | None] = mapped_column(Text, nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    comment:   Mapped[str]  = mapped_column(String(512), default="", nullable=False)
    created_at:Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    topic:  Mapped["Topic"]      = relationship(back_populates="versions")
    author: Mapped["User | None"] = relationship(back_populates="topic_versions")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# form_schemas  (Phase 3 — DataForms)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FormSchema(Base):
    """
    A named form definition, optionally scoped to a web.
    e.g. "BugReport", "MeetingMinutes", "PersonProfile"
    """
    __tablename__ = "form_schemas"
    __table_args__ = (
        UniqueConstraint("name", "web_id", name="uq_form_schema_name_web"),
    )

    id:          Mapped[str]        = _uuid_col(primary_key=True)
    name:        Mapped[str]        = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str]        = mapped_column(Text, default="", nullable=False)
    web_id:      Mapped[str | None] = mapped_column(String(36), ForeignKey("webs.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at:  Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at:  Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    web:    Mapped["Web | None"]      = relationship("Web")
    fields: Mapped[list["FormField"]] = relationship(
        back_populates="schema", cascade="all, delete-orphan",
        order_by="FormField.position",
    )
    topics: Mapped[list["Topic"]]     = relationship(back_populates="form_schema")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# form_fields
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FormField(Base):
    """
    A single field within a FormSchema.

    field_type: text | textarea | number | date | select | multiselect | checkbox | url | email
    options:    comma-separated list for select/multiselect fields
    """
    __tablename__ = "form_fields"
    __table_args__ = (
        UniqueConstraint("schema_id", "name", name="uq_form_field_schema_name"),
    )

    id:           Mapped[str]        = _uuid_col(primary_key=True)
    schema_id:    Mapped[str]        = mapped_column(String(36), ForeignKey("form_schemas.id", ondelete="CASCADE"), nullable=False, index=True)
    name:         Mapped[str]        = mapped_column(String(128), nullable=False)   # key used in topic_meta
    label:        Mapped[str]        = mapped_column(String(256), nullable=False)   # display label
    field_type:   Mapped[str]        = mapped_column(String(32),  nullable=False, default="text")
    options:      Mapped[str]        = mapped_column(Text, default="", nullable=False)  # comma-sep for select
    default_value:Mapped[str]        = mapped_column(Text, default="", nullable=False)
    is_required:  Mapped[bool]       = mapped_column(Boolean, default=False, nullable=False)
    position:     Mapped[int]        = mapped_column(Integer, default=0, nullable=False)

    schema: Mapped["FormSchema"] = relationship(back_populates="fields")

    def options_list(self) -> list[str]:
        return [o.strip() for o in self.options.split(",") if o.strip()]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# topic_meta  (DataForms structured metadata)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TopicMeta(Base):
    __tablename__ = "topic_meta"
    __table_args__ = (
        UniqueConstraint("topic_id", "key", name="uq_topic_meta_key"),
    )

    id:       Mapped[str] = _uuid_col(primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    key:      Mapped[str] = mapped_column(String(128), nullable=False)
    value:    Mapped[str] = mapped_column(Text, default="", nullable=False)

    topic: Mapped["Topic"] = relationship(back_populates="meta")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# attachments
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint("topic_id", "filename", name="uq_attachments_topic_file"),
    )

    id:           Mapped[str] = _uuid_col(primary_key=True)
    topic_id:     Mapped[str] = mapped_column(String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    filename:     Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream", nullable=False)
    size_bytes:   Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)  # relative to attachment_root
    uploaded_by:  Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    comment:      Mapped[str] = mapped_column(String(512), default="", nullable=False)
    uploaded_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    topic:            Mapped["Topic"]       = relationship(back_populates="attachments")
    uploaded_by_user: Mapped["User | None"] = relationship(back_populates="attachments")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# acl
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ACL(Base):
    """
    Access control entry.

    resource_type : "web" | "topic"
    resource_id   : UUID of the web or topic
    principal     : "user:<username>", "group:<name>", or "*" (everyone)
    permission    : "view" | "edit" | "create" | "rename" | "delete" | "admin"
    allow         : True → ALLOW, False → DENY
    """
    __tablename__ = "acl"
    __table_args__ = (
        Index("ix_acl_resource", "resource_type", "resource_id"),
        UniqueConstraint("resource_type", "resource_id", "principal", "permission", name="uq_acl_entry"),
    )

    id:            Mapped[str]  = _uuid_col(primary_key=True)
    resource_type: Mapped[str]  = mapped_column(String(16), nullable=False)   # "web" | "topic"
    resource_id:   Mapped[str]  = mapped_column(String(36), nullable=False)   # UUID (no FK for polymorphism)
    principal:     Mapped[str]  = mapped_column(String(128), nullable=False)  # "user:jdoe" | "group:Dev" | "*"
    permission:    Mapped[str]  = mapped_column(String(32), nullable=False)   # "view" | "edit" | ...
    allow:         Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Convenience back-ref (view-only, no FK defined on this side)
    web: Mapped["Web | None"] = relationship(
        "Web",
        primaryjoin="and_(ACL.resource_type=='web', foreign(ACL.resource_id)==Web.id)",
        viewonly=True,
        back_populates="acl",
    )
