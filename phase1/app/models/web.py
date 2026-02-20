#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Web model
=========
A Web is a named namespace containing topics.
Webs can be nested (parent_id → self-referential).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Web(Base):
    __tablename__ = "webs"
    __table_args__ = (UniqueConstraint("name", name="uq_web_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("webs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # ── Relationships ───────────────────────────────────────────────────────
    topics: Mapped[list["Topic"]] = relationship(          # noqa: F821
        back_populates="web", cascade="all, delete-orphan", lazy="raise"
    )
    parent: Mapped[Optional["Web"]] = relationship(
        "Web", remote_side="Web.id", back_populates="children", lazy="raise"
    )
    children: Mapped[list["Web"]] = relationship(
        "Web", back_populates="parent", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<Web {self.name!r}>"




