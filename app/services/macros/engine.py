"""
MacroEngine
===========
The core expansion loop.  Scans text for %MACRO% and %MACRO{params}%
patterns and replaces them with their rendered output.

Expansion is recursive — macros may produce text containing other macros.
A depth limit prevents infinite loops.
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from .context import MacroContext
from .params import parse_params
from .registry import macro_registry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern explanation:
#   %MACRO%              — no-param form
#   %MACRO{...}%         — param form (non-greedy, no nested %)
#
# We match the longest form first (with params) then the bare form.
# Names are uppercase letters, digits, and underscores.
# ---------------------------------------------------------------------------
_MACRO_PATTERN = re.compile(
    r'%([A-Z][A-Z0-9_]*)(?:\{([^%]*?)\})?%'
)

MAX_EXPANSION_DEPTH = 10     # guard against infinite macro loops
MAX_EXPANSION_PASSES = 20    # max total re-scan passes per render


class MacroEngine:
    """
    Expand all macros embedded in a piece of wiki text.

    Usage::

        engine = MacroEngine()
        result = await engine.expand(raw_text, ctx)
    """

    def __init__(self, registry=None) -> None:
        self._registry = registry or macro_registry

    # ----------------------------------------------------------------- public

    async def expand(self, text: str, ctx: MacroContext) -> str:
        """
        Fully expand all macros in *text*, return rendered string.

        Performs multiple passes so that macros whose output contains
        other macros are also expanded (up to MAX_EXPANSION_PASSES).
        """
        if not text:
            return text

        for _pass in range(MAX_EXPANSION_PASSES):
            expanded = await self._expand_once(text, ctx)
            if expanded == text:
                break   # stable — no more macros to expand
            text = expanded
        else:
            logger.warning("Macro expansion reached pass limit (%d)", MAX_EXPANSION_PASSES)

        return text

    # ----------------------------------------------------------------- private

    async def _expand_once(self, text: str, ctx: MacroContext) -> str:
        """Run a single scan-and-replace pass over *text*."""
        result_parts: list[str] = []
        last_end = 0

        for match in _MACRO_PATTERN.finditer(text):
            # Append literal text before this match
            result_parts.append(text[last_end:match.start()])

            name = match.group(1)
            raw_params = match.group(2) or ""
            params = parse_params(raw_params)

            replacement = await self._registry.call(name, params, ctx)
            result_parts.append(replacement)

            last_end = match.end()

        # Append any trailing literal text
        result_parts.append(text[last_end:])
        return "".join(result_parts)
