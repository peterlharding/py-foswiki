"""
MacroParamParser
================
Parses the parameter string inside %MACRO{...}%.

Supported forms
---------------
  key="value"           → {"key": "value"}
  key='value'           → {"key": "value"}
  flag                  → {"flag": "on"}
  "positional value"    → {"_default": "positional value"}
  value (bare word)     → {"_default": "value"}

Combinable:
  %SEARCH{"my query" web="Main" type="regex" limit="10"}%
  → {"_default": "my query", "web": "Main", "type": "regex", "limit": "10"}
"""

from __future__ import annotations

import re

# Matches: key="value", key='value', key=bareword
_KV_DOUBLE  = re.compile(r'(\w+)="([^"]*)"')
_KV_SINGLE  = re.compile(r"(\w+)='([^']*)'")
_KV_BARE    = re.compile(r'(\w+)=(\S+)')
# Quoted positional: "value" or 'value'
_POS_DOUBLE = re.compile(r'^"([^"]*)"')
_POS_SINGLE = re.compile(r"^'([^']*)'")
# Flag (bare word, not key=value)
_FLAG       = re.compile(r'^(\w+)$')


def parse_params(raw: str) -> dict[str, str]:
    """
    Parse a macro parameter string into a dict.

    Parameters
    ----------
    raw : str
        The raw parameter string, e.g. ``"my query" web="Main" limit="5"``

    Returns
    -------
    dict[str, str]
        Parsed parameters. Positional/default value keyed as ``"_default"``.
    """
    if not raw or not raw.strip():
        return {}

    params: dict[str, str] = {}
    text = raw.strip()

    while text:
        text = text.strip()
        if not text:
            break

        matched = False

        # key="value"
        m = _KV_DOUBLE.match(text)
        if m:
            params[m.group(1)] = m.group(2)
            text = text[m.end():]
            matched = True

        # key='value'
        if not matched:
            m = _KV_SINGLE.match(text)
            if m:
                params[m.group(1)] = m.group(2)
                text = text[m.end():]
                matched = True

        # key=bareword
        if not matched:
            m = _KV_BARE.match(text)
            if m:
                params[m.group(1)] = m.group(2)
                text = text[m.end():]
                matched = True

        # "positional"
        if not matched:
            m = _POS_DOUBLE.match(text)
            if m:
                params.setdefault("_default", m.group(1))
                text = text[m.end():]
                matched = True

        # 'positional'
        if not matched:
            m = _POS_SINGLE.match(text)
            if m:
                params.setdefault("_default", m.group(1))
                text = text[m.end():]
                matched = True

        # flag (bare word not followed by =)
        if not matched:
            m = _FLAG.match(text)
            if m:
                word = m.group(1)
                if text[m.end():m.end()+1] != "=":
                    params[word] = "on"
                    text = text[m.end():]
                    matched = True

        if not matched:
            # Skip unrecognised character to avoid infinite loop
            text = text[1:]

    return params


def get_param(params: dict[str, str], *keys: str, default: str = "") -> str:
    """
    Retrieve the first matching key from params.

    The first key in *keys is the canonical name; subsequent keys are aliases.
    Only falls back to ``"_default"`` when ``"_default"`` is explicitly listed
    in *keys* — this prevents query/list positional values from accidentally
    satisfying unrelated parameter lookups (e.g. limit, separator, etc.).
    Falls back to *default* if nothing matches.
    """
    for key in keys:
        if key in params:
            return params[key]
    return default
