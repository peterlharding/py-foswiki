"""
INCLUDE macro
-------------
Transcludes the rendered (or raw) content of another topic into the current topic.

%INCLUDE{"Web.TopicName"}%
%INCLUDE{"TopicName"}%                        — same web as current topic
%INCLUDE{"TopicName" section="MySect"}%       — named section only
%INCLUDE{"TopicName" raw="on"}%               — insert raw TML, skip rendering
%INCLUDE{"TopicName" warn="off"}%             — suppress "not found" warning

Named sections use the delimiters:
    %STARTSECTION{"MySect"}%  ... content ...  %ENDSECTION{"MySect"}%
"""

from __future__ import annotations

import re
import html
import logging

from .registry import MacroRegistry
from .params import get_param
from .context import MacroContext

logger = logging.getLogger(__name__)

_MAX_INCLUDE_DEPTH = 5

# Matches %STARTSECTION{"name"}% ... %ENDSECTION{"name"}%
_SECTION_RE = re.compile(
    r'%STARTSECTION\{"([^"]+)"\}%(.*?)%ENDSECTION\{"[^"]+"\}%',
    re.DOTALL,
)
# Strip STARTSECTION/ENDSECTION markers from rendered content
_SECTION_STRIP = re.compile(r'%(?:START|END)SECTION\{[^}]*\}%')


def register(registry: MacroRegistry) -> None:

    @registry.register("INCLUDE")
    async def include_macro(params: dict, ctx: MacroContext) -> str:
        target  = get_param(params, "_default", "topic")
        section = get_param(params, "section", default="")
        raw_mode = get_param(params, "raw", default="off") in ("on", "1", "true")
        warn    = get_param(params, "warn", default="on") not in ("off", "0", "false")

        if not target:
            return _warn("INCLUDE: no topic specified", warn)

        # Depth guard
        if ctx._include_depth >= _MAX_INCLUDE_DEPTH:
            return _warn(f"INCLUDE: maximum include depth ({_MAX_INCLUDE_DEPTH}) reached", warn)

        # Parse "Web.Topic" or just "Topic"
        if "." in target:
            web, topic = target.split(".", 1)
        else:
            web, topic = ctx.web, target

        # Fetch raw content from DB
        content = await _fetch_topic_content(ctx, web, topic)
        if content is None:
            return _warn(f"INCLUDE: topic not found: {web}.{topic}", warn)

        # Extract named section if requested
        if section:
            content = _extract_section(content, section)
            if content is None:
                return _warn(f"INCLUDE: section '{section}' not found in {web}.{topic}", warn)

        # Strip section markers from included content
        content = _SECTION_STRIP.sub("", content)

        if raw_mode:
            return content

        # Render through the full pipeline using the injected render function
        if ctx._render_fn is not None:
            child_ctx = _child_context(ctx, web, topic)
            try:
                return await ctx._render_fn(web, topic, child_ctx, preloaded_content=content)
            except Exception as exc:
                logger.exception("INCLUDE render error for %s.%s", web, topic)
                return _warn(f"INCLUDE render error: {exc}", warn)

        # Fallback: return raw if no render function is available
        return content


async def _fetch_topic_content(ctx: MacroContext, web: str, topic: str) -> str | None:
    """Fetch the latest raw content for web.topic from the database."""
    if ctx.db is None:
        return None
    try:
        from sqlalchemy import text
        result = await ctx.db.execute(
            text("""
                SELECT tv.content
                FROM topic_versions tv
                JOIN topics t ON t.id = tv.topic_id
                JOIN webs w ON w.id = t.web_id
                WHERE w.name = :web AND t.name = :topic
                ORDER BY tv.version DESC
                LIMIT 1
            """),
            {"web": web, "topic": topic},
        )
        row = result.first()
        return row[0] if row else None
    except Exception:
        logger.exception("DB error fetching %s.%s for INCLUDE", web, topic)
        return None


def _extract_section(content: str, section_name: str) -> str | None:
    """Return text between %STARTSECTION{"name"}% and %ENDSECTION{"name"}%."""
    for match in _SECTION_RE.finditer(content):
        if match.group(1) == section_name:
            return match.group(2).strip()
    return None


def _child_context(ctx: MacroContext, web: str, topic: str) -> MacroContext:
    """Create a child context for the included topic (deeper depth)."""
    import copy
    child = copy.copy(ctx)
    child.web = web
    child.topic = topic
    child.topic_id = None
    child._include_depth = ctx._include_depth + 1
    return child


def _warn(message: str, show: bool) -> str:
    if show:
        return f'<span class="macro-warning">[{html.escape(message)}]</span>'
    return ""
