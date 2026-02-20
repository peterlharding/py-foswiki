"""
FORMAT / FORMATLIST macro
-------------------------
%FORMATLIST{"item1, item2, item3"
  format="   * $item"
  separator=","
  sort="on"
  unique="on"
  header="Items:\n"
  footer=""}%

$item  — the individual list element (trimmed)
$index — 1-based position
$n     — newline

Also registers:
  %NOP%          — no-operation (consumed silently, used to separate macros)
  %JQICON{"name"}% — placeholder for icon support (returns empty span)
"""

from __future__ import annotations

from .registry import MacroRegistry
from .params import get_param


def register(registry: MacroRegistry) -> None:

    @registry.register("FORMATLIST")
    def formatlist_macro(params: dict, ctx) -> str:
        raw       = params.get("list") or params.get("_default", "")
        fmt       = params.get("format", "$item")
        split_sep = params.get("split", ",")           # separator for INPUT splitting
        out_sep   = params.get("separator", "\n").replace(r"\n", "\n")  # separator for OUTPUT joining
        do_sort   = params.get("sort",   "off") in ("on", "1", "true")
        do_unique = params.get("unique", "off") in ("on", "1", "true")
        header    = params.get("header", "").replace(r"\n", "\n")
        footer    = params.get("footer", "").replace(r"\n", "\n")
        limit     = params.get("limit", "")

        if not raw:
            return ""

        items = [i.strip() for i in raw.split(split_sep) if i.strip()]

        if do_unique:
            seen = set()
            deduped = []
            for i in items:
                if i not in seen:
                    seen.add(i)
                    deduped.append(i)
            items = deduped

        if do_sort:
            items = sorted(items)

        if limit:
            items = items[:int(limit)]

        rows = []
        for idx, item in enumerate(items, start=1):
            row = fmt.replace("$item", item).replace("$index", str(idx)).replace("$n", "\n")
            rows.append(row)

        result = out_sep.join(rows)
        return (header or "") + result + (footer or "")

    @registry.register("NOP")
    def nop_macro(params, ctx):
        """No-operation — used to break up adjacent macro syntax."""
        return ""

    @registry.register("JQICON")
    def jqicon_macro(params, ctx):
        name = get_param(params, "_default", "name", default="")
        return f'<span class="jqi jqi-{name}"></span>'

    @registry.register("BR")
    def br_macro(params, ctx):
        return "<br />"

    @registry.register("VBAR")
    def vbar_macro(params, ctx):
        return "|"

    @registry.register("BULLET")
    def bullet_macro(params, ctx):
        return "•"

    @registry.register("NBSP")
    def nbsp_macro(params, ctx):
        return "&nbsp;"

    @registry.register("LAQUO")
    def laquo_macro(params, ctx):
        return "«"

    @registry.register("RAQUO")
    def raquo_macro(params, ctx):
        return "»"
