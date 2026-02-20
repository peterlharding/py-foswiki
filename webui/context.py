#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
Page context helper — carries per-request state into templates.
"""
# -----------------------------------------------------------------------------

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PageContext:
    title: str = "PyFoswiki"
    user: Optional[dict] = None          # populated from session
    flash: Optional[str] = None          # one-shot status message
    flash_type: str = "info"             # info | success | error | warning
    web: Optional[str] = None
    topic: Optional[str] = None

    def is_authenticated(self) -> bool:
        return self.user is not None

    def is_admin(self) -> bool:
        return bool(self.user and self.user.get("is_admin"))

    def to_dict(self, request) -> dict:
        return {
            "request": request,
            "ctx": self,
            "title": self.title,
            "user": self.user,
            "flash": self.flash,
            "flash_type": self.flash_type,
        }
