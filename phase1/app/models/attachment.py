#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

o"""
Attachment model
================
Files uploaded to a topic are stored on disk and tracked here.
storage_path is relative to the configured upload_dir.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)   # relative path on disk
    comment: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    uploaded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # ── Relationships ───────────────────────────────────────────────────────
    topic: Mapped["Topic"] = relationship(back_populates="attachments", lazy="raise")  # noqa: F821
    uploaded_by_user: Mapped[Optional["User"]] = relationship(           # noqa: F821
        back_populates="attachments", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<Attachment {self.filename!r} on topic={self.topic_id}>"



