#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""Initial schema — Phase 1 tables

Revision ID: 001_initial
Revises:
Create Date: 2025-01-01 00:00:00
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# -----------------------------------------------------------------------------

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


# -----------------------------------------------------------------------------

def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",            sa.String(36),  primary_key=True),
        sa.Column("username",      sa.String(64),  nullable=False),
        sa.Column("email",         sa.String(255), nullable=False),
        sa.Column("display_name",  sa.String(128), nullable=False, server_default=""),
        sa.Column("wiki_name",     sa.String(128), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active",     sa.Boolean(),   nullable=False, server_default=sa.text("TRUE")),
        sa.Column("is_admin",      sa.Boolean(),   nullable=False, server_default=sa.text("FALSE")),
        sa.Column("groups",        sa.Text(),      nullable=False, server_default=""),
        sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at",    sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email",    "users", ["email"],    unique=True)

    # ── webs ───────────────────────────────────────────────────────────────────
    op.create_table(
        "webs",
        sa.Column("id",          sa.String(36),  primary_key=True),
        sa.Column("name",        sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text(),      nullable=False, server_default=""),
        sa.Column("parent_id",   sa.String(36),  sa.ForeignKey("webs.id"), nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_webs_name", "webs", ["name"], unique=True)

    # ── topics ─────────────────────────────────────────────────────────────────
    op.create_table(
        "topics",
        sa.Column("id",         sa.String(36),  primary_key=True),
        sa.Column("web_id",     sa.String(36),  sa.ForeignKey("webs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",       sa.String(256), nullable=False),
        sa.Column("created_by", sa.String(36),  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("web_id", "name", name="uq_topics_web_name"),
    )
    op.create_index("ix_topics_web_id", "topics", ["web_id"])
    op.create_index("ix_topics_name",   "topics", ["name"])

    # ── topic_versions ─────────────────────────────────────────────────────────
    op.create_table(
        "topic_versions",
        sa.Column("id",         sa.String(36),     primary_key=True),
        sa.Column("topic_id",   sa.String(36),     sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version",    sa.Integer(),      nullable=False),
        sa.Column("content",    sa.Text(),         nullable=False, server_default=""),
        sa.Column("rendered",   sa.Text(),         nullable=True),
        sa.Column("author_id",  sa.String(36),     sa.ForeignKey("users.id"), nullable=True),
        sa.Column("comment",    sa.String(512),    nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("topic_id", "version", name="uq_topic_versions_topic_ver"),
    )
    op.create_index("ix_topic_versions_topic_id",     "topic_versions", ["topic_id"])
    op.create_index("ix_topic_versions_topic_latest", "topic_versions", ["topic_id", "version"])

    # ── topic_meta ─────────────────────────────────────────────────────────────
    op.create_table(
        "topic_meta",
        sa.Column("id",       sa.String(36),  primary_key=True),
        sa.Column("topic_id", sa.String(36),  sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key",      sa.String(128), nullable=False),
        sa.Column("value",    sa.Text(),      nullable=False, server_default=""),
        sa.UniqueConstraint("topic_id", "key", name="uq_topic_meta_key"),
    )
    op.create_index("ix_topic_meta_topic_id", "topic_meta", ["topic_id"])

    # ── attachments ────────────────────────────────────────────────────────────
    op.create_table(
        "attachments",
        sa.Column("id",           sa.String(36),  primary_key=True),
        sa.Column("topic_id",     sa.String(36),  sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename",     sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes",   sa.BigInteger(),nullable=False, server_default="0"),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("uploaded_by",  sa.String(36),  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("comment",      sa.String(512), nullable=False, server_default=""),
        sa.Column("uploaded_at",  sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("topic_id", "filename", name="uq_attachments_topic_file"),
    )
    op.create_index("ix_attachments_topic_id", "attachments", ["topic_id"])

    # ── acl ────────────────────────────────────────────────────────────────────
    op.create_table(
        "acl",
        sa.Column("id",            sa.String(36),  primary_key=True),
        sa.Column("resource_type", sa.String(16),  nullable=False),
        sa.Column("resource_id",   sa.String(36),  nullable=False),
        sa.Column("principal",     sa.String(128), nullable=False),
        sa.Column("permission",    sa.String(32),  nullable=False),
        sa.Column("allow",         sa.Boolean(),   nullable=False, server_default=sa.text("TRUE")),
        sa.UniqueConstraint("resource_type", "resource_id", "principal", "permission", name="uq_acl_entry"),
    )
    op.create_index("ix_acl_resource", "acl", ["resource_type", "resource_id"])


# -----------------------------------------------------------------------------

def downgrade() -> None:
    op.drop_table("acl")
    op.drop_table("attachments")
    op.drop_table("topic_meta")
    op.drop_table("topic_versions")
    op.drop_table("topics")
    op.drop_table("webs")
    op.drop_table("users")


# -----------------------------------------------------------------------------
