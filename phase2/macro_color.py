"""
Utility macros
--------------
%RED% text %ENDCOLOR%       — colored text spans
%BLUE% ... %ENDCOLOR%
%GREEN% ... %ENDCOLOR%    (and all HTML named colors)

%WEB%                       — current web name
%TOPIC%                     — current topic name
%BASETOPIC%                 — alias for %TOPIC%
%TOPICURL%                  — full URL to current topic
%SCRIPTURL{"view"}%         — base script URL
%PUBURL%                    — public attachments URL
%ATTACHURL%                 — attachment URL for current topic

%IF{"condition" then="yes" else="no"}%
  condition can be: context, defined (VARIABLE), or istopic (Web.Topic)
"""

from __future__ import annotations

import html as html_module

from .registry import MacroRegistry
from .params import get_param

# Supported named colors → CSS color values
_COLORS: dict[str, str] = {
    "RED":     "#cc0000",
    "GREEN":   "#006600",
    "BLUE":    "#0000cc",
    "YELLOW":  "#cccc00",
    "ORANGE":  "#cc6600",
    "PINK":    "#cc0066",
    "PURPLE":  "#660099",
    "TEAL":    "#006666",
    "NAVY":    "#000066",
    "GRAY":    "#666666",
    "SILVER":  "#aaaaaa",
    "LIME":    "#00cc00",
    "AQUA":    "#00cccc",
    "MAROON":  "#660000",
    "OLIVE":   "#666600",
    "WHITE":   "#ffffff",
    "BLACK":   "#000000",
}


def register(registry: MacroRegistry) -> None:

    # ----------------------------------------------------------------- colors

    def _make_color_macro(color_name: str, css_value: str):
        def color_macro(params, ctx):
            # %RED% opens a span; the renderer expects a matching %ENDCOLOR%
            return f'<span style="color:{css_value}">'
        return color_macro

    for name, css in _COLORS.items():
        registry.register(name)(_make_color_macro(name, css))

    @registry.register("ENDCOLOR")
    def endcolor_macro(params, ctx):
        return "</span>"

    # ------------------------------------------------------------------- web

    @registry.register("WEB")
    def web_macro(params, ctx):
        return html_module.escape(ctx.web)

    @registry.register("TOPIC")
    def topic_macro(params, ctx):
        return html_module.escape(ctx.topic)

    @registry.register("BASETOPIC")
    def basetopic_macro(params, ctx):
        return html_module.escape(ctx.topic)

    @registry.register("TOPICURL")
    def topicurl_macro(params, ctx):
        return ctx.topic_url(ctx.web, ctx.topic)

    @registry.register("SCRIPTURL")
    def scripturl_macro(params, ctx):
        action = get_param(params, "_default", "script", default="view")
        return f"{ctx.base_url}/{html_module.escape(action)}"

    @registry.register("PUBURL")
    def puburl_macro(params, ctx):
        return f"{ctx.base_url}/pub"

    @registry.register("ATTACHURL")
    def attachurl_macro(params, ctx):
        return f"{ctx.base_url}/pub/{ctx.web}/{ctx.topic}"

    @registry.register("WIKILOGOURL")
    def wikilogourl_macro(params, ctx):
        return ctx.base_url or "/"

    # -------------------------------------------------------------------- IF

    @registry.register("IF")
    async def if_macro(params, ctx):
        """
        %IF{"condition" then="yes" else="no"}%

        Supported condition forms:
          defined VARNAME         — always false (variables not yet impl)
          context contextname     — reserved for future
          istopic Web.TopicName   — check if topic exists in DB
          "literal string"        — truthy if non-empty
        """
        condition = get_param(params, "_default", "condition")
        then_val  = get_param(params, "then", default="")
        else_val  = get_param(params, "else", default="")

        result = await _evaluate_condition(condition, ctx)
        return then_val if result else else_val


async def _evaluate_condition(condition: str, ctx) -> bool:
    if not condition:
        return False

    cond = condition.strip()

    if cond.startswith("istopic "):
        target = cond[8:].strip().strip('"\'')
        return await _topic_exists(ctx, target)

    if cond.startswith("defined "):
        # Variable existence — not yet implemented, always false
        return False

    if cond.startswith("context "):
        context_name = cond[8:].strip()
        known = {"authenticated": ctx.current_user is not None}
        return known.get(context_name, False)

    # Plain string truthy check
    return bool(cond.strip('"\''))


async def _topic_exists(ctx, target: str) -> bool:
    if not ctx.db:
        return False
    web, topic = target.split(".", 1) if "." in target else (ctx.web, target)
    try:
        from sqlalchemy import text
        result = await ctx.db.execute(
            text("SELECT 1 FROM topics t JOIN webs w ON w.id=t.web_id WHERE w.name=:web AND t.name=:topic LIMIT 1"),
            {"web": web, "topic": topic},
        )
        return result.first() is not None
    except Exception:
        return False
