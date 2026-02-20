#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Topic Rendering Pipeline
========================
Orchestrates the full Phase 2 render pipeline:

  raw TML/Markdown
        ↓
  1. Pre-render plugin hooks
        ↓
  2. Macro expansion  (%MACRO{params}%)
        ↓
  3. Bracket link conversion  [[target][label]]
        ↓
  4. Markdown rendering  (mistune)
        ↓
  5. WikiWord auto-linking  (post-Markdown, on rendered HTML)
        ↓
  6. Post-render plugin hooks
        ↓
  HTML output

Usage::

    pipeline = RenderPipeline(base_url=settings.base_url, db=db_session)

    html = await pipeline.render(
        web="Main",
        topic="WebHome",
        content=raw_text,
        current_user=user_dict,
    )
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import re
import logging
from typing import Any, Optional

try:
    import mistune
    _HAS_MISTUNE = True
except ImportError:
    _HAS_MISTUNE = False

from app.services.macros import MacroEngine, MacroContext, macro_registry, register_all_builtins
from app.services.wikiword import WikiWordLinker


# -----------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bracket link pattern:  [[Web.Topic][Label]]  or  [[Topic]]
# ---------------------------------------------------------------------------

_BRACKET_LINK_RE = re.compile(
    r'\[\[([^\]]+)\](?:\[([^\]]+)\])?\]'
)


# -----------------------------------------------------------------------------

class RenderPipeline:
    """
    The central rendering service. Instantiate once per application (or per
    request if you want per-request DB sessions).

    Parameters
    ----------
    base_url : str
        Root URL of the wiki, e.g. "https://wiki.example.com".
    db : Any
        SQLAlchemy AsyncSession.
    search_service : Any, optional
        Object with ``.search(...)`` async method (for %SEARCH%).
    plugin_manager : Any, optional
        Object with ``.pre_render()`` and ``.post_render()`` async methods.
    """

    _builtins_registered = False

    # -------------------------------------------------------------------------

    def __init__(
        self,
        base_url: str = "",
        db: Any = None,
        search_service: Any = None,
        plugin_manager: Any = None,
    ) -> None:
        self.base_url = base_url
        self.db = db
        self.search_service = search_service
        self.plugin_manager = plugin_manager

        # Register built-in macros once globally
        if not RenderPipeline._builtins_registered:
            register_all_builtins()
            RenderPipeline._builtins_registered = True

        self._macro_engine = MacroEngine(registry=macro_registry)
        self._md = _build_markdown_renderer()

    # ----------------------------------------------------------------- public

    async def render(
        self,
        web: str,
        topic: str,
        content: str,
        current_user: Optional[dict] = None,
        topic_id=None,
        preloaded_content: Optional[str] = None,
    ) -> str:
        """
        Render *content* through the full pipeline and return HTML.

        Parameters
        ----------
        web, topic : str
            Identifies the topic being rendered (used for relative links).
        content : str
            Raw TML/Markdown source.
        current_user : dict | None
            Authenticated user record.
        topic_id : UUID | None
            DB id of the topic (for macros that need it).
        preloaded_content : str | None
            Override content (used internally by %INCLUDE%).
        """
        raw = preloaded_content or content
        if not raw:
            return ""

        ctx = self._make_context(web, topic, topic_id, current_user, raw)

        # ── 1. Pre-render plugin hooks ─────────────────────────────────────
        text = await self._pre_render(raw, ctx)

        # ── 2. Macro expansion ─────────────────────────────────────────────
        text = await self._macro_engine.expand(text, ctx)

        # ── 3. Bracket link conversion  [[target][label]] → Markdown link ──
        text = self._expand_bracket_links(text, web, ctx)

        # ── 4. Markdown → HTML ─────────────────────────────────────────────
        html = self._render_markdown(text)

        # ── 5. WikiWord auto-linking (post-Markdown, on rendered HTML) ─────
        linker = WikiWordLinker(
            base_url=self.base_url,
            default_web=web,
            topic_exists_fn=self._topic_exists,
        )
        html = await linker.process_html(html)

        # ── 6. Post-render plugin hooks ────────────────────────────────────
        html = await self._post_render(html, ctx)

        return html

    # ---------------------------------------------------------------- private

    def _make_context(self, web, topic, topic_id, current_user, raw_content) -> MacroContext:
        ctx = MacroContext(
            web=web,
            topic=topic,
            topic_id=topic_id,
            base_url=self.base_url,
            current_user=current_user,
            db=self.db,
            search_service=self.search_service,
        )
        ctx._raw_content = raw_content          # type: ignore[attr-defined]
        ctx._render_fn = self._include_render   # type: ignore[attr-defined]
        return ctx

    # -------------------------------------------------------------------------

    async def _include_render(
        self, web: str, topic: str, child_ctx: MacroContext,
        preloaded_content: str = "",
    ) -> str:
        """Render function injected into MacroContext for %INCLUDE%."""
        return await self.render(
            web=web,
            topic=topic,
            content=preloaded_content,
            current_user=child_ctx.current_user,
            topic_id=child_ctx.topic_id,
            preloaded_content=preloaded_content,
        )

    # -------------------------------------------------------------------------

    async def _topic_exists(self, web: str, topic: str) -> bool:
        if self.db is None:
            return True
        try:
            from sqlalchemy import text
            result = await self.db.execute(
                text("""
                    SELECT 1 FROM topics t
                    JOIN webs w ON w.id = t.web_id
                    WHERE w.name = :web AND t.name = :topic
                    LIMIT 1
                """),
                {"web": web, "topic": topic},
            )
            return result.first() is not None
        except Exception:
            return True

    # -------------------------------------------------------------------------

    def _expand_bracket_links(self, text: str, default_web: str, ctx: MacroContext) -> str:
        """
        Convert [[Target][Label]] and [[Target]] bracket links to Markdown.

        [[Main.SomeTopic][My Link]] → [My Link](/view/Main/SomeTopic)
        [[SomeTopic]]               → [SomeTopic](/view/{web}/SomeTopic)
        """
        def replace(m: re.Match) -> str:
            target = m.group(1).strip()
            label  = (m.group(2) or "").strip()

            if target.startswith(("http://", "https://", "ftp://")):
                display = label or target
                return f"[{display}]({target})"

            if "." in target:
                web_part, topic_part = target.split(".", 1)
            else:
                web_part  = default_web
                topic_part = target

            url = f"{self.base_url}/view/{web_part}/{topic_part}"
            display = label or target
            return f"[{display}]({url})"

        return _BRACKET_LINK_RE.sub(replace, text)

    # -------------------------------------------------------------------------

    async def _pre_render(self, text: str, ctx: MacroContext) -> str:
        if self.plugin_manager and hasattr(self.plugin_manager, "pre_render"):
            return await self.plugin_manager.pre_render(text, ctx)
        return text

    # -------------------------------------------------------------------------

    async def _post_render(self, html: str, ctx: MacroContext) -> str:
        if self.plugin_manager and hasattr(self.plugin_manager, "post_render"):
            return await self.plugin_manager.post_render(html, ctx)
        return html

    # -------------------------------------------------------------------------

    def _render_markdown(self, text: str) -> str:
        if _HAS_MISTUNE:
            return self._md(text)
        logger.warning("mistune not installed — returning raw text")
        import html
        return f"<pre>{html.escape(text)}</pre>"

    # -------------------------------------------------------------------------


# -----------------------------------------------------------------------------

def _build_markdown_renderer():
    """
    Build a mistune renderer with table, strikethrough, and footnotes support.
    Falls back to a simple lambda if mistune is not installed.
    """
    if not _HAS_MISTUNE:
        return lambda text: text

    if hasattr(mistune, "create_markdown"):
        # mistune >= 3.x
        return mistune.create_markdown(
            plugins=["table", "strikethrough", "footnotes", "task_lists"],
        )
    else:
        # mistune 2.x
        return mistune.create_markdown(
            plugins=["table", "strikethrough", "footnotes"],
        )


# -----------------------------------------------------------------------------
