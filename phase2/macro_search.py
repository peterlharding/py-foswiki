"""
SEARCH macro
------------
%SEARCH{"query" web="Main" type="text" scope="all"
         limit="20" order="modified" reverse="on"
         format="| $topic | $date | $summary |"
         header="| *Topic* | *Date* | *Summary* |"
         footer="" separator="\n" nonoise="on"}%

type:
  text    — simple substring match (default)
  regex   — Python regex match against content
  query   — structured field match  field="value"

scope:
  all     — topic name + content (default)
  topic   — topic name only
  content — content only

format tokens:
  $web $topic $title $date $modified $author $summary $rev $url $n $comma
"""

from __future__ import annotations

import re
import html
from datetime import datetime

from .registry import MacroRegistry
from .params import get_param


# Default row format if caller doesn't specify
_DEFAULT_FORMAT = "   * [[$web.$topic][$topic]] - $summary"
_DEFAULT_HEADER = ""
_DEFAULT_SEPARATOR = "\n"

_SUMMARY_LEN = 160


def register(registry: MacroRegistry) -> None:

    @registry.register("SEARCH")
    async def search_macro(params, ctx):
        query   = params.get("search") or params.get("_default", "")
        web     = params.get("web", ctx.web)
        stype   = params.get("type", "text")
        scope   = params.get("scope", "all")
        limit   = int(params.get("limit", "20"))
        order   = params.get("order", "modified")
        reverse = params.get("reverse", "off") in ("on", "1", "true")
        fmt     = params.get("format", _DEFAULT_FORMAT)
        header  = params.get("header", _DEFAULT_HEADER)
        footer  = params.get("footer", "")
        sep     = params.get("separator", _DEFAULT_SEPARATOR).replace(r"\n", "\n")
        nonoise = params.get("nonoise", "off") in ("on", "1", "true")

        if not query:
            return "" if nonoise else '<span class="macro-error">[SEARCH: no query specified]</span>'

        if ctx.search_service is None:
            return _fallback_search(query, nonoise)

        try:
            results = await ctx.search_service.search(
                query=query,
                web=web,
                search_type=stype,
                scope=scope,
                limit=limit,
                order_by=order,
                reverse=reverse,
            )
        except Exception as exc:
            return f'<span class="macro-error">[SEARCH error: {html.escape(str(exc))}]</span>'

        if not results:
            return "" if nonoise else '<span class="search-no-results">No topics found.</span>'

        rows = [_format_row(fmt, r, ctx) for r in results]
        parts = []
        if header:
            parts.append(header)
        parts.append(sep.join(rows))
        if footer:
            parts.append(footer)

        return "\n".join(parts)


def _format_row(fmt: str, result: dict, ctx) -> str:
    """Apply $token substitution for one search result."""
    topic    = result.get("name", "")
    web      = result.get("web", ctx.web)
    modified = result.get("modified_at")
    author   = result.get("author", "")
    content  = result.get("content", "")
    rev      = str(result.get("version", 1))

    date_str = modified.strftime("%Y-%m-%d") if isinstance(modified, datetime) else str(modified or "")
    summary  = _make_summary(content)
    url      = ctx.topic_url(web, topic)

    replacements = {
        "$web":      web,
        "$topic":    topic,
        "$title":    topic,
        "$date":     date_str,
        "$modified": date_str,
        "$author":   author,
        "$summary":  summary,
        "$rev":      rev,
        "$url":      url,
        "$n":        "\n",
        "$comma":    ",",
    }
    row = fmt
    for token, value in replacements.items():
        row = row.replace(token, value)
    return row


def _make_summary(content: str, length: int = _SUMMARY_LEN) -> str:
    """Strip markup and return a short plain-text excerpt."""
    # Strip TML/HTML tags
    text = re.sub(r'%[A-Z_]+(?:\{[^}]*\})?%', '', content)   # macros
    text = re.sub(r'<[^>]+>', '', text)                        # HTML
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > length:
        text = text[:length].rsplit(' ', 1)[0] + '…'
    return text


def _fallback_search(query: str, nonoise: bool) -> str:
    """Returned when no search service is available."""
    if nonoise:
        return ""
    return (
        f'<span class="macro-error">'
        f'[SEARCH: no search service configured for query "{html.escape(query)}"]'
        f'</span>'
    )
