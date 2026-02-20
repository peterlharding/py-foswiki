"""
WikiWord Auto-Linker
====================
Converts CamelCase WikiWords into hyperlinks, matching Foswiki behaviour.

Rules
-----
1. A WikiWord is two or more "humps": starts with uppercase, has at least one
   more uppercase letter after one or more lowercase letters.
   Regex: [A-Z][a-z]+[A-Z][A-Za-z0-9]*

2. Qualified: Web.TopicName  → link to that web's topic.

3. [[Link][Label]] — explicit bracket notation is left to Markdown to handle.
   We only process bare WikiWords here.

4. Preceded by ! → escaped, not linked (strips the !).

5. WikiWords inside code spans, HTML tags, URLs, and existing <a> tags
   are never linked.

6. If the topic does not exist in the database, the link is rendered as a
   "create" link (with a ? suffix), matching Foswiki behaviour.
   When a DB is not available, all WikiWords are linked unconditionally.
"""

from __future__ import annotations

import re
from typing import Callable, Awaitable

# ---------------------------------------------------------------------------
# Core WikiWord pattern
# ---------------------------------------------------------------------------
_WIKIWORD_CORE = r'[A-Z][a-z]+(?:[A-Z][A-Za-z0-9]+)+'
_WIKIWORD_RE = re.compile(
    r'(?<![\w/])'                # not preceded by word-char or slash
    r'(?:([A-Za-z][A-Za-z0-9]*)\.)?'  # optional Web. prefix
    r'(' + _WIKIWORD_CORE + r')'
)

# Escape marker: !WikiWord → remove ! and skip linking
_ESCAPE_MARKER_RE = re.compile(r'!(' + _WIKIWORD_CORE + r')')

# Regions to skip: code spans, inline code, HTML tags, URLs, existing anchors
_SKIP_REGIONS = re.compile(
    r'(`[^`]*`'            # backtick code spans
    r'|```[\s\S]*?```'     # fenced code blocks
    r'|<[^>]+>'            # HTML tags
    r'|https?://\S+'       # bare URLs
    r'|\[\[.*?\]\]'        # bracket wiki links
    r')',
    re.DOTALL,
)

# Escape sequences:  !WikiWord → WikiWord (no link)
_ESCAPE_RE = re.compile(r'!(' + _WIKIWORD_CORE + r')')


class WikiWordLinker:
    """
    Transform bare WikiWords in a text string into HTML anchor tags.

    Parameters
    ----------
    base_url : str
        Root URL of the wiki (e.g. "https://wiki.example.com").
    default_web : str
        Web to use for unqualified WikiWords.
    topic_exists_fn : callable, optional
        ``async (web, topic) -> bool`` — if provided, unknown topics get a
        "create" link instead of a normal link.
    """

    def __init__(
        self,
        base_url: str,
        default_web: str = "Main",
        topic_exists_fn: Callable[[str, str], Awaitable[bool]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_web = default_web
        self._topic_exists = topic_exists_fn

    async def process(self, text: str) -> str:
        """Return *text* with WikiWords replaced by HTML links."""
        if not text:
            return text

        # Step 1: split text into "skip" and "process" regions
        parts = _split_regions(text)

        out_parts: list[str] = []
        for is_skip, chunk in parts:
            if is_skip:
                out_parts.append(chunk)
            else:
                # Strip escape markers and remember escaped words
                chunk, escaped = _strip_escapes(chunk)
                chunk = await self._link_wikiwords(chunk, escaped)
                out_parts.append(chunk)

        return "".join(out_parts)

    async def _link_wikiwords(self, text: str, escaped: set[str] | None = None) -> str:
        """Replace WikiWord patterns with anchor tags."""
        if not text:
            return text
        if escaped is None:
            escaped = set()

        result: list[str] = []
        last_end = 0

        for match in _WIKIWORD_RE.finditer(text):
            result.append(text[last_end:match.start()])

            web   = match.group(1) or self.default_web
            topic = match.group(2)

            # Skip if this word was escaped with !
            if topic in escaped:
                result.append(match.group(0))
                last_end = match.end()
                continue

            href, css_class = await self._make_href(web, topic)

            if match.group(1):
                label = f"{web}.{topic}"
            else:
                label = topic

            result.append(f'<a href="{href}" class="{css_class}">{label}</a>')
            last_end = match.end()

        result.append(text[last_end:])
        return "".join(result)

    async def _make_href(self, web: str, topic: str) -> tuple[str, str]:
        """Return (url, css_class) for the link."""
        view_url   = f"{self.base_url}/view/{web}/{topic}"
        create_url = f"{self.base_url}/edit/{web}/{topic}?create=1"

        if self._topic_exists is not None:
            try:
                exists = await self._topic_exists(web, topic)
            except Exception:
                exists = True   # fail open — assume it exists
            if exists:
                return view_url, "wiki-link"
            else:
                return create_url, "wiki-link wiki-link-missing"

        return view_url, "wiki-link"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_escapes(text: str) -> tuple[str, set[str]]:
    """
    Remove ! escape markers and collect the escaped word names.
    Returns (cleaned_text, {escaped_word_names}).
    """
    escaped: set[str] = set()
    def _replace(m: re.Match) -> str:
        escaped.add(m.group(1))
        return m.group(1)   # keep the word, drop the !
    cleaned = _ESCAPE_MARKER_RE.sub(_replace, text)
    return cleaned, escaped


def _split_regions(text: str) -> list[tuple[bool, str]]:
    """
    Split *text* into (is_skip, chunk) pairs.
    Chunks where is_skip=True must not be WikiWord-linked.
    """
    parts: list[tuple[bool, str]] = []
    last_end = 0

    for m in _SKIP_REGIONS.finditer(text):
        if m.start() > last_end:
            parts.append((False, text[last_end:m.start()]))
        parts.append((True, m.group(0)))
        last_end = m.end()

    if last_end < len(text):
        parts.append((False, text[last_end:]))

    return parts
