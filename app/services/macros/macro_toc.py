"""
TOC macro
---------
Generates an HTML table of contents by scanning the topic's headings.

%TOC%
%TOC{"Web.TopicName"}%     — TOC for a different topic
%TOC{depth="3"}%           — only include headings up to h3
%TOC{title="Contents"}%    — add a title above the TOC

The TOC is built from Markdown headings (# ## ###) and Foswiki-style
headings (---+ ---++ ---+++) in the rendered source.

This macro is special: it also injects id="" anchors into the headings
of the rendered HTML.  Because we need to see the full text, it works
as a post-render hook as well as a macro; the macro emits a placeholder
that the renderer replaces after Markdown has been applied.

For simplicity this implementation builds the TOC directly from the
raw TML/Markdown source during macro expansion.  The heading anchor
IDs match what Python-Markdown (or mistune) generates.
"""

from __future__ import annotations

import re
import html
from dataclasses import dataclass, field

from .registry import MacroRegistry
from .params import get_param

# Matches Markdown ATX headings: # Title, ## Title, etc.
_MD_HEADING = re.compile(r'^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$', re.MULTILINE)
# Matches Foswiki/TWiki-style headings: ---+ Title, ---++ Title
_TWI_HEADING = re.compile(r'^-{3,}(\++)\s+(.+)$', re.MULTILINE)

_MAX_DEPTH = 6


@dataclass
class Heading:
    level: int
    text: str
    anchor: str


def register(registry: MacroRegistry) -> None:

    @registry.register("TOC")
    async def toc_macro(params: dict, ctx) -> str:
        target = get_param(params, "_default", "topic", default="")
        depth  = int(get_param(params, "depth", default=str(_MAX_DEPTH)))
        title  = get_param(params, "title", default="")
        min_h  = int(get_param(params, "mindepth", default="1"))

        depth = max(1, min(depth, _MAX_DEPTH))

        # Fetch content (current topic or a named one)
        if target:
            web, topic = (target.split(".", 1) if "." in target else (ctx.web, target))
            content = await _fetch_content(ctx, web, topic)
        else:
            # We don't have direct access to the raw content here,
            # so the caller must have placed it on the context.
            content = getattr(ctx, "_raw_content", "")

        if not content:
            return ""

        headings = _extract_headings(content, min_level=min_h, max_level=depth)
        if not headings:
            return ""

        return _render_toc(headings, title, min_h)


def _extract_headings(content: str, min_level: int = 1, max_level: int = 6) -> list[Heading]:
    headings: list[Heading] = []

    for m in _MD_HEADING.finditer(content):
        level = len(m.group(1))
        text  = m.group(2).strip()
        if min_level <= level <= max_level:
            headings.append(Heading(level=level, text=text, anchor=_make_anchor(text)))

    for m in _TWI_HEADING.finditer(content):
        level = len(m.group(1))   # count '+' signs
        text  = m.group(2).strip()
        if min_level <= level <= max_level:
            headings.append(Heading(level=level, text=text, anchor=_make_anchor(text)))

    # Sort by their position in the document (both regexes were global; merge by position)
    # Simple approach: re-scan to get ordered positions
    return _ordered_headings(content, min_level, max_level)


def _ordered_headings(content: str, min_level: int, max_level: int) -> list[Heading]:
    """Return headings in document order."""
    combined = []

    for m in _MD_HEADING.finditer(content):
        level = len(m.group(1))
        if min_level <= level <= max_level:
            combined.append((m.start(), level, m.group(2).strip()))

    for m in _TWI_HEADING.finditer(content):
        level = len(m.group(1))
        if min_level <= level <= max_level:
            combined.append((m.start(), level, m.group(2).strip()))

    combined.sort(key=lambda x: x[0])
    seen_anchors: dict[str, int] = {}
    result = []
    for _, level, text in combined:
        anchor = _make_anchor(text)
        count = seen_anchors.get(anchor, 0)
        seen_anchors[anchor] = count + 1
        if count:
            anchor = f"{anchor}-{count}"
        result.append(Heading(level=level, text=text, anchor=anchor))
    return result


def _make_anchor(text: str) -> str:
    """Convert heading text to a URL-safe anchor ID (matches Python-Markdown)."""
    anchor = text.lower()
    anchor = re.sub(r'[^\w\s-]', '', anchor)
    anchor = re.sub(r'[\s_-]+', '-', anchor).strip('-')
    return anchor


def _render_toc(headings: list[Heading], title: str, base_level: int) -> str:
    lines = ['<div class="wiki-toc">']
    if title:
        lines.append(f'  <div class="wiki-toc-title">{html.escape(title)}</div>')
    lines.append('  <ul>')

    prev_level = headings[0].level if headings else 1

    for h in headings:
        indent = "    " * (h.level - base_level)
        safe_text = html.escape(h.text)
        lines.append(
            f'{indent}  <li class="toc-level-{h.level}">'
            f'<a href="#{h.anchor}">{safe_text}</a></li>'
        )

    lines.append('  </ul>')
    lines.append('</div>')
    return "\n".join(lines)


async def _fetch_content(ctx, web: str, topic: str) -> str:
    if ctx.db is None:
        return ""
    try:
        from sqlalchemy import text
        result = await ctx.db.execute(
            text("""
                SELECT tv.content FROM topic_versions tv
                JOIN topics t ON t.id = tv.topic_id
                JOIN webs w ON w.id = t.web_id
                WHERE w.name = :web AND t.name = :topic
                ORDER BY tv.version DESC LIMIT 1
            """),
            {"web": web, "topic": topic},
        )
        row = result.first()
        return row[0] if row else ""
    except Exception:
        return ""
