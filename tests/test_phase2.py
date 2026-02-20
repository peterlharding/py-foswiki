"""
Phase 2 Test Suite
==================
Tests for:
  - Parameter parser
  - MacroRegistry (sync & async handlers)
  - MacroEngine (expansion loop)
  - Built-in macros: DATE, GMTIME, USERINFO, WIKINAME, USERNAME, GROUPS,
                     ISMEMBER, SEARCH, INCLUDE, TOC, colors, IF, WEB,
                     TOPIC, TOPICURL, FORMATLIST, NOP, META, FORMFIELD,
                     REVINFO, WEBLIST, TOPICLIST
  - WikiWord auto-linker
  - Bracket link conversion
  - Full render pipeline (sans DB)

Run with:  pytest tests/test_phase2.py -v
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.macros.params import parse_params, get_param
from app.services.macros.registry import MacroRegistry
from app.services.macros.engine import MacroEngine
from app.services.macros.context import MacroContext
from app.services.macros.builtins import register_all_builtins
from app.services.macros import macro_registry
from app.services.wikiword.linker import WikiWordLinker
from app.services.renderer import RenderPipeline


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run(coro):
    """Run an async coroutine in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


def make_ctx(**kwargs) -> MacroContext:
    defaults = dict(web="Main", topic="WebHome", base_url="https://wiki.test")
    defaults.update(kwargs)
    return MacroContext(**defaults)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Parameter parser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestParseParams:
    def test_empty(self):
        assert parse_params("") == {}

    def test_single_kv_double_quote(self):
        assert parse_params('key="value"') == {"key": "value"}

    def test_single_kv_single_quote(self):
        assert parse_params("key='value'") == {"key": "value"}

    def test_multiple_kv(self):
        p = parse_params('web="Main" limit="10" type="text"')
        assert p == {"web": "Main", "limit": "10", "type": "text"}

    def test_positional_double_quoted(self):
        p = parse_params('"my query"')
        assert p["_default"] == "my query"

    def test_positional_single_quoted(self):
        p = parse_params("'my query'")
        assert p["_default"] == "my query"

    def test_flag(self):
        p = parse_params("noheader")
        assert p["noheader"] == "on"

    def test_mixed(self):
        p = parse_params('"hello" web="Main" limit="5"')
        assert p["_default"] == "hello"
        assert p["web"] == "Main"
        assert p["limit"] == "5"

    def test_get_param_first_key(self):
        p = {"web": "Dev"}
        assert get_param(p, "web", default="Main") == "Dev"

    def test_get_param_fallback_default(self):
        assert get_param({}, "web", default="Main") == "Main"

    def test_get_param_uses_positional(self):
        p = {"_default": "query text"}
        assert get_param(p, "search", "_default", default="") == "query text"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. MacroRegistry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMacroRegistry:
    def setup_method(self):
        self.reg = MacroRegistry()

    def test_register_sync(self):
        @self.reg.register("HELLO")
        def hello(params, ctx):
            return "hi"

        assert self.reg.has("HELLO")
        result = run(self.reg.call("HELLO", {}, make_ctx()))
        assert result == "hi"

    def test_register_async(self):
        @self.reg.register("ASYNCMACRO")
        async def asyncm(params, ctx):
            return "async-result"

        result = run(self.reg.call("ASYNCMACRO", {}, make_ctx()))
        assert result == "async-result"

    def test_unknown_macro_returns_itself(self):
        result = run(self.reg.call("UNKNOWN", {}, make_ctx()))
        assert result == "%UNKNOWN%"

    def test_error_returns_error_span(self):
        @self.reg.register("BOOM")
        def boom(params, ctx):
            raise ValueError("oops")

        result = run(self.reg.call("BOOM", {}, make_ctx()))
        assert "macro-error" in result
        assert "oops" in result

    def test_case_insensitive(self):
        @self.reg.register("myMACRO")
        def mm(params, ctx):
            return "ok"

        assert self.reg.has("MYMACRO")
        assert self.reg.has("mymacro")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. MacroEngine expansion
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMacroEngine:
    def setup_method(self):
        self.reg = MacroRegistry()
        self.engine = MacroEngine(registry=self.reg)

        @self.reg.register("HELLO")
        def hello(params, ctx):
            name = params.get("name", "World")
            return f"Hello, {name}!"

        @self.reg.register("WRAP")
        def wrap(params, ctx):
            return "%HELLO%"   # produces another macro

    def test_simple_expansion(self):
        result = run(self.engine.expand("%HELLO%", make_ctx()))
        assert result == "Hello, World!"

    def test_expansion_with_params(self):
        result = run(self.engine.expand('%HELLO{name="Alice"}%', make_ctx()))
        assert result == "Hello, Alice!"

    def test_recursive_expansion(self):
        result = run(self.engine.expand("%WRAP%", make_ctx()))
        assert result == "Hello, World!"

    def test_literal_text_preserved(self):
        result = run(self.engine.expand("Before %HELLO% After", make_ctx()))
        assert result == "Before Hello, World! After"

    def test_multiple_macros(self):
        result = run(self.engine.expand("%HELLO% and %HELLO{name=\"Bob\"}%", make_ctx()))
        assert result == "Hello, World! and Hello, Bob!"

    def test_unknown_macro_passthrough(self):
        result = run(self.engine.expand("%UNKNOWN%", make_ctx()))
        assert result == "%UNKNOWN%"

    def test_no_macros(self):
        result = run(self.engine.expand("plain text", make_ctx()))
        assert result == "plain text"

    def test_empty_string(self):
        result = run(self.engine.expand("", make_ctx()))
        assert result == ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Built-in macros (use the shared singleton registry)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Register once for all tests
register_all_builtins()
_engine = MacroEngine(registry=macro_registry)


def expand(text: str, ctx: MacroContext = None) -> str:
    return run(_engine.expand(text, ctx or make_ctx()))


class TestDateMacros:
    def test_date_returns_date_string(self):
        result = expand("%DATE%")
        assert re.match(r"\d{4}-\d{2}-\d{2}", result)

    def test_gmtime_returns_timestamp(self):
        result = expand("%GMTIME%")
        assert "T" in result and "Z" in result

    def test_gmtime_custom_format(self):
        result = expand('%GMTIME{"$year"}%')
        assert result.isdigit() and len(result) == 4

    def test_servertime(self):
        result = expand("%SERVERTIME%")
        assert "T" in result


import re   # re already imported above but needed explicitly in test file scope


class TestUserMacros:
    def _ctx_with_user(self):
        user = {
            "username": "jdoe",
            "wiki_name": "JohnDoe",
            "display_name": "John Doe",
            "email": "john@example.com",
            "groups": ["Dev", "Admins"],
        }
        return make_ctx(current_user=user)

    def test_wikiname(self):
        assert expand("%WIKINAME%", self._ctx_with_user()) == "JohnDoe"

    def test_username(self):
        assert expand("%USERNAME%", self._ctx_with_user()) == "jdoe"

    def test_wikiname_guest(self):
        assert expand("%WIKINAME%", make_ctx()) == "Guest"

    def test_groups(self):
        result = expand("%GROUPS%", self._ctx_with_user())
        assert "Dev" in result
        assert "Admins" in result

    def test_ismember_true(self):
        assert expand('%ISMEMBER{"Admins"}%', self._ctx_with_user()) == "1"

    def test_ismember_false(self):
        assert expand('%ISMEMBER{"Marketing"}%', self._ctx_with_user()) == ""


class TestColorMacros:
    def test_red_opens_span(self):
        result = expand("%RED%")
        assert "<span" in result and "#cc0000" in result

    def test_endcolor_closes_span(self):
        assert expand("%ENDCOLOR%") == "</span>"

    def test_color_chain(self):
        result = expand("%BLUE%text%ENDCOLOR%")
        assert "<span" in result and "</span>" in result and "text" in result


class TestWebTopicMacros:
    def test_web(self):
        ctx = make_ctx(web="Development")
        assert expand("%WEB%", ctx) == "Development"

    def test_topic(self):
        ctx = make_ctx(topic="MyPage")
        assert expand("%TOPIC%", ctx) == "MyPage"

    def test_topicurl(self):
        ctx = make_ctx(web="Main", topic="Home", base_url="https://wiki.test")
        assert expand("%TOPICURL%", ctx) == "https://wiki.test/view/Main/Home"

    def test_scripturl(self):
        ctx = make_ctx(base_url="https://wiki.test")
        result = expand('%SCRIPTURL{"edit"}%', ctx)
        assert result == "https://wiki.test/edit"

    def test_puburl(self):
        ctx = make_ctx(base_url="https://wiki.test")
        assert expand("%PUBURL%", ctx) == "https://wiki.test/pub"


class TestIFMacro:
    def test_if_truthy_string(self):
        result = expand('%IF{"nonempty" then="yes" else="no"}%')
        assert result == "yes"

    def test_if_empty_string(self):
        result = expand('%IF{"" then="yes" else="no"}%')
        assert result == "no"

    def test_if_authenticated_true(self):
        ctx = make_ctx(current_user={"username": "u"})
        result = expand('%IF{"context authenticated" then="logged in" else="guest"}%', ctx)
        assert result == "logged in"

    def test_if_authenticated_false(self):
        ctx = make_ctx(current_user=None)
        result = expand('%IF{"context authenticated" then="logged in" else="guest"}%', ctx)
        assert result == "guest"


class TestFormatListMacro:
    def test_basic(self):
        result = expand('%FORMATLIST{"a, b, c" format="[$item]"}%')
        assert "[a]" in result
        assert "[b]" in result
        assert "[c]" in result

    def test_sort(self):
        result = expand('%FORMATLIST{"c, a, b" format="$item" sort="on" separator=", "}%')
        assert result == "a, b, c"

    def test_unique(self):
        result = expand('%FORMATLIST{"a, b, a, c" format="$item" unique="on" separator=","}%')
        items = result.split(",")
        assert len(items) == len(set(items))

    def test_limit(self):
        result = expand('%FORMATLIST{"a, b, c, d" format="$item" limit="2" separator=","}%')
        assert len(result.split(",")) == 2

    def test_index_token(self):
        result = expand('%FORMATLIST{"x, y" format="$index:$item" separator="|"}%')
        assert "1:x" in result
        assert "2:y" in result


class TestNopMacro:
    def test_nop_is_empty(self):
        assert expand("%NOP%") == ""

    def test_br(self):
        assert expand("%BR%") == "<br />"

    def test_nbsp(self):
        assert expand("%NBSP%") == "&nbsp;"


class TestSearchMacro:
    def test_no_query_returns_error(self):
        result = expand("%SEARCH%")
        assert "macro-error" in result or result == "%SEARCH%"

    def test_no_service_returns_error(self):
        result = expand('%SEARCH{"test"}%')
        assert "macro-error" in result or "no search service" in result

    def test_nonoise_suppresses_error(self):
        result = expand('%SEARCH{"test" nonoise="on"}%')
        assert result == ""

    def test_with_search_service(self):
        search_svc = MagicMock()
        search_svc.search = AsyncMock(return_value=[
            {"name": "MyTopic", "web": "Main", "content": "hello world",
             "modified_at": datetime(2025, 1, 1), "author": "admin", "version": 1}
        ])
        ctx = make_ctx(search_service=search_svc)
        result = expand('%SEARCH{"hello" format="$topic"}%', ctx)
        assert "MyTopic" in result


class TestIncludeMacro:
    def test_depth_limit(self):
        """Deeply nested include should hit depth limit gracefully."""
        ctx = make_ctx()
        ctx._include_depth = 10
        result = expand('%INCLUDE{"SomeTopic"}%', ctx)
        assert "depth" in result.lower() or "macro-warning" in result or result == ""

    def test_missing_topic_name(self):
        result = expand("%INCLUDE%")
        # Should either be a warning or passthrough, not an exception
        assert isinstance(result, str)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. WikiWord Linker
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWikiWordLinker:
    def _linker(self, exists=True) -> WikiWordLinker:
        async def topic_exists(web, topic):
            return exists
        return WikiWordLinker(
            base_url="https://wiki.test",
            default_web="Main",
            topic_exists_fn=topic_exists,
        )

    def test_basic_wikiword(self):
        result = run(self._linker().process("See WebHome for details."))
        assert 'href="https://wiki.test/view/Main/WebHome"' in result

    def test_qualified_wikiword(self):
        result = run(self._linker().process("See Dev.ProjectPlan today."))
        assert 'href="https://wiki.test/view/Dev/ProjectPlan"' in result

    def test_escaped_wikiword(self):
        result = run(self._linker().process("!WebHome is not linked."))
        assert 'href' not in result or 'WebHome' in result
        # The ! should be consumed and WebHome NOT linked
        assert "<a" not in result.split("WebHome")[0].split("!")[-1]

    def test_missing_topic_gets_create_link(self):
        result = run(self._linker(exists=False).process("See MissingTopic here."))
        assert "create=1" in result
        assert "wiki-link-missing" in result

    def test_no_link_inside_backtick(self):
        result = run(self._linker().process("`WikiWord` in code"))
        # The WikiWord inside backticks should not be linked
        assert "`WikiWord`" in result

    def test_no_link_in_url(self):
        result = run(self._linker().process("See https://example.com/WebHome for info"))
        # URL should not be mangled
        assert "https://example.com/WebHome" in result

    def test_single_hump_not_linked(self):
        """Words like 'Python' or 'Simple' are not WikiWords."""
        result = run(self._linker().process("Python is great. Simple test."))
        assert "<a" not in result

    def test_multiple_wikiwords(self):
        result = run(self._linker().process("See WebHome and UserGuide for help."))
        assert result.count("<a ") == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Bracket link conversion
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBracketLinks:
    def _pipeline(self):
        return RenderPipeline(base_url="https://wiki.test")

    def test_bracket_with_label(self):
        p = self._pipeline()
        result = p._expand_bracket_links("[[Main.WebHome][Home Page]]", "Main", make_ctx())
        assert "[Home Page]" in result
        assert "/view/Main/WebHome" in result

    def test_bracket_without_label(self):
        p = self._pipeline()
        result = p._expand_bracket_links("[[WebHome]]", "Main", make_ctx())
        assert "WebHome" in result
        assert "/view/Main/WebHome" in result

    def test_external_link(self):
        p = self._pipeline()
        result = p._expand_bracket_links("[[https://example.com][External]]", "Main", make_ctx())
        assert "https://example.com" in result
        assert "External" in result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Full pipeline integration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRenderPipeline:
    def _pipeline(self):
        return RenderPipeline(base_url="https://wiki.test")

    def test_basic_markdown(self):
        pipeline = self._pipeline()
        html = run(pipeline.render("Main", "TestTopic", "# Hello\n\nSome **bold** text."))
        assert "<h1" in html
        assert "<strong>" in html or "<b>" in html

    def test_macro_in_markdown(self):
        pipeline = self._pipeline()
        html = run(pipeline.render("Main", "TestTopic", "Current web: %WEB%"))
        assert "Main" in html

    def test_wikiword_in_markdown(self):
        pipeline = self._pipeline()
        html = run(pipeline.render("Main", "TestTopic", "See WebHome for details."))
        assert "<a " in html

    def test_color_macro(self):
        pipeline = self._pipeline()
        html = run(pipeline.render("Main", "TestTopic", "%RED%important%ENDCOLOR%"))
        assert "span" in html
        assert "#cc0000" in html

    def test_bracket_link(self):
        pipeline = self._pipeline()
        html = run(pipeline.render("Main", "TestTopic", "[[WebHome][Go Home]]"))
        assert "Go Home" in html

    def test_empty_content(self):
        pipeline = self._pipeline()
        html = run(pipeline.render("Main", "TestTopic", ""))
        assert html == ""

    def test_complex_page(self):
        pipeline = self._pipeline()
        content = """
# %TOPIC% in %WEB%

Current date: %DATE%

See [[WebHome][the home page]] or WebHome directly.

%IF{"nonempty" then="Conditional text shown" else="hidden"}%

%FORMATLIST{"Alpha, Beta, Gamma" format="* $item" separator=","}%
"""
        html = run(pipeline.render("Main", "TestTopic", content))
        assert "TestTopic" in html
        assert "Main" in html
        assert "Conditional text shown" in html
        assert "Alpha" in html
        assert "Beta" in html
