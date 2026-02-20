#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------


"""
User model
==========
Stores user accounts with bcrypt-hashed passwords.
Groups are stored as a simple comma-delimited string (easy to query).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    wiki_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    groups_str: Mapped[str] = mapped_column(Text, nullable=False, default="")  # "Admins,Dev"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # ── Relationships ───────────────────────────────────────────────────────
    topic_versions: Mapped[list["TopicVersion"]] = relationship(  # noqa: F821
        back_populates="author", lazy="raise"
    )
    attachments: Mapped[list["Attachment"]] = relationship(        # noqa: F821
        back_populates="uploaded_by_user", lazy="raise"
    )

    # ── Helpers ─────────────────────────────────────────────────────────────

    @property
    def groups(self) -> list[str]:
        if not self.groups_str:
            return []
        return [g.strip() for g in self.groups_str.split(",") if g.strip()]

    @groups.setter
    def groups(self, value: list[str]) -> None:
        self.groups_str = ",".join(value)

    def to_context_dict(self) -> dict:
        """Return dict suitable for MacroContext.current_user."""
        return {
            "id": str(self.id),
            "username": self.username,
            "display_name": self.display_name,
            "wiki_name": self.wiki_name,
            "email": self.email,
            "groups": self.groups,
        }

    def __repr__(self) -> str:
        return f"<User {self.username!r}>"



