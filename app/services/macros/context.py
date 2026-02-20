"""
MacroContext — per-request state passed to every macro handler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID


@dataclass
class MacroContext:
    """
    Carries the render-time context into every macro call.

    Attributes
    ----------
    web : str
        Name of the current web (e.g. "Main").
    topic : str
        Name of the current topic (e.g. "WebHome").
    topic_id : UUID | None
        Database ID of the current topic, if it exists.
    base_url : str
        Root URL of the wiki (e.g. "https://wiki.example.com").
    current_user : dict | None
        The authenticated user record (id, username, display_name, email, groups).
    db : Any
        AsyncSession database handle — macros that need DB access use this.
    search_service : Any | None
        Injected search service (for %SEARCH%).
    settings : dict
        Site-wide configuration values.
    _include_depth : int
        Internal counter to prevent infinite %INCLUDE% recursion.
    _render_fn : callable | None
        Reference back to the top-level render function so %INCLUDE%
        can render included topics through the full pipeline.
    """

    web: str = "Main"
    topic: str = "WebHome"
    topic_id: Optional[UUID] = None
    base_url: str = ""
    current_user: Optional[dict] = None
    db: Any = None
    search_service: Any = None
    settings: dict = field(default_factory=dict)
    _include_depth: int = 0
    _render_fn: Any = None  # Callable[[str, str, MacroContext], Awaitable[str]]

    # ------------------------------------------------------------------ helpers

    def topic_url(self, web: str, topic: str) -> str:
        return f"{self.base_url}/view/{web}/{topic}"

    def user_display(self) -> str:
        if self.current_user:
            return self.current_user.get("display_name") or self.current_user.get("username", "Guest")
        return "Guest"

    def user_groups(self) -> list[str]:
        if self.current_user:
            return self.current_user.get("groups", [])
        return []
