"""
process_html — applies WikiWord linking to rendered HTML,
skipping content inside existing <a> tags, <code>, <pre>, and <script> blocks.
"""

import re
from .linker import WikiWordLinker

# Matches block-level tags whose content must NOT be WikiWord-linked
_SKIP_HTML_TAGS = re.compile(
    r'(<a\b[^>]*>.*?</a>'      # existing anchor tags
    r'|<code\b[^>]*>.*?</code>'
    r'|<pre\b[^>]*>.*?</pre>'
    r'|<script\b[^>]*>.*?</script>'
    r'|<style\b[^>]*>.*?</style>'
    r')',
    re.DOTALL | re.IGNORECASE,
)


async def process_html(linker: WikiWordLinker, html: str) -> str:
    """
    Apply WikiWord linking to *html* while preserving existing tags.

    Splits the HTML into skip-regions (existing links, code, pre, script)
    and plain-text/tag regions.  Only text content outside skip-regions
    is processed for WikiWords.
    """
    if not html:
        return html

    parts: list[str] = []
    last_end = 0

    for m in _SKIP_HTML_TAGS.finditer(html):
        before = html[last_end:m.start()]
        if before:
            # Process this segment for WikiWords (it may contain HTML tags
            # like <p>, <li>, etc. — split those out, link only text nodes)
            parts.append(await _link_text_nodes(linker, before))
        parts.append(m.group(0))   # keep existing link/code intact
        last_end = m.end()

    tail = html[last_end:]
    if tail:
        parts.append(await _link_text_nodes(linker, tail))

    return "".join(parts)


_HTML_TAG_RE = re.compile(r'(<[^>]+>)')


async def _link_text_nodes(linker: WikiWordLinker, fragment: str) -> str:
    """
    Within *fragment* (which may contain simple HTML tags like <p>, <li>),
    link WikiWords only in the text nodes, not inside tag attributes.
    """
    result: list[str] = []
    for part in _HTML_TAG_RE.split(fragment):
        if part.startswith("<"):
            result.append(part)            # HTML tag — keep as-is
        else:
            result.append(await linker.process(part))   # text node — link
    return "".join(result)


# Monkey-patch onto the class for clean pipeline usage
WikiWordLinker.process_html = lambda self, html: process_html(self, html)
