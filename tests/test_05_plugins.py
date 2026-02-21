#!/usr/bin/env python
# -----------------------------------------------------------------------------
"""
Phase 5 — Plugin System Tests
==============================
  - PluginManager hook dispatch (pre_render, post_render, lifecycle hooks)
  - Error isolation: broken plugin does not prevent other plugins running
  - Plugin registration, introspection (len, plugins property)
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Plugin system
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPluginSystem:
    """Tests run against a fresh PluginManager(plugin_dir=None) so no
    file-based plugins are loaded and tests are fully isolated."""

    def _mgr(self):
        from app.services.plugins import PluginManager
        return PluginManager(plugin_dir=None)

    async def test_empty_manager_passthrough_pre_render(self):
        mgr = self._mgr()
        assert await mgr.pre_render("hello", ctx={}) == "hello"

    async def test_empty_manager_passthrough_post_render(self):
        mgr = self._mgr()
        assert await mgr.post_render("<p>hi</p>", ctx={}) == "<p>hi</p>"

    async def test_pre_render_hook_transforms_text(self):
        from app.services.plugins import BasePlugin, PluginManager

        class UpperPlugin(BasePlugin):
            name = "upper"
            async def pre_render(self, text, ctx):
                return text.upper()

        mgr = PluginManager(plugin_dir=None)
        mgr.register(UpperPlugin())
        assert await mgr.pre_render("hello", ctx={}) == "HELLO"

    async def test_post_render_hook_transforms_html(self):
        from app.services.plugins import BasePlugin, PluginManager

        class WrapPlugin(BasePlugin):
            name = "wrap"
            async def post_render(self, html, ctx):
                return f"<div>{html}</div>"

        mgr = PluginManager(plugin_dir=None)
        mgr.register(WrapPlugin())
        assert await mgr.post_render("<p>hi</p>", ctx={}) == "<div><p>hi</p></div>"

    async def test_multiple_plugins_chained_in_order(self):
        from app.services.plugins import BasePlugin, PluginManager

        class AddA(BasePlugin):
            name = "a"
            async def pre_render(self, text, ctx): return text + "A"

        class AddB(BasePlugin):
            name = "b"
            async def pre_render(self, text, ctx): return text + "B"

        mgr = PluginManager(plugin_dir=None)
        mgr.register(AddA())
        mgr.register(AddB())
        assert await mgr.pre_render("X", ctx={}) == "XAB"

    async def test_broken_plugin_error_is_isolated(self):
        from app.services.plugins import BasePlugin, PluginManager

        class BrokenPlugin(BasePlugin):
            name = "broken"
            async def pre_render(self, text, ctx):
                raise RuntimeError("boom")

        class GoodPlugin(BasePlugin):
            name = "good"
            async def pre_render(self, text, ctx): return text + "_ok"

        mgr = PluginManager(plugin_dir=None)
        mgr.register(BrokenPlugin())
        mgr.register(GoodPlugin())
        # Broken plugin error is swallowed; good plugin still runs
        result = await mgr.pre_render("X", ctx={})
        assert result == "X_ok"

    async def test_after_save_hook_dispatched(self):
        from app.services.plugins import BasePlugin, PluginManager

        calls: list = []

        class SavePlugin(BasePlugin):
            name = "save"
            async def after_save(self, web, topic, version, user=None):
                calls.append((web, topic, version))

        mgr = PluginManager(plugin_dir=None)
        mgr.register(SavePlugin())
        await mgr.after_save("MyWeb", "MyTopic", version=2)
        assert calls == [("MyWeb", "MyTopic", 2)]

    async def test_after_create_hook_dispatched(self):
        from app.services.plugins import BasePlugin, PluginManager

        calls: list = []

        class CreatePlugin(BasePlugin):
            name = "create"
            async def after_create(self, web, topic, version, user=None):
                calls.append((web, topic))

        mgr = PluginManager(plugin_dir=None)
        mgr.register(CreatePlugin())
        await mgr.after_create("W", "T", version=1)
        assert calls == [("W", "T")]

    async def test_after_delete_hook_dispatched(self):
        from app.services.plugins import BasePlugin, PluginManager

        calls: list = []

        class DeletePlugin(BasePlugin):
            name = "delete"
            async def after_delete(self, web, topic, user=None):
                calls.append((web, topic))

        mgr = PluginManager(plugin_dir=None)
        mgr.register(DeletePlugin())
        await mgr.after_delete("W", "T")
        assert calls == [("W", "T")]

    async def test_after_upload_hook_dispatched(self):
        from app.services.plugins import BasePlugin, PluginManager

        calls: list = []

        class UploadPlugin(BasePlugin):
            name = "upload"
            async def after_upload(self, web, topic, attachment):
                calls.append((web, topic, attachment))

        mgr = PluginManager(plugin_dir=None)
        mgr.register(UploadPlugin())
        await mgr.after_upload("W", "T", "file.txt")
        assert calls == [("W", "T", "file.txt")]

    async def test_len_reflects_registered_count(self):
        from app.services.plugins import BasePlugin, PluginManager

        class P1(BasePlugin):
            name = "p1"

        class P2(BasePlugin):
            name = "p2"

        mgr = PluginManager(plugin_dir=None)
        assert len(mgr) == 0
        mgr.register(P1())
        assert len(mgr) == 1
        mgr.register(P2())
        assert len(mgr) == 2

    async def test_plugins_property_returns_copy(self):
        from app.services.plugins import BasePlugin, PluginManager

        class P(BasePlugin):
            name = "p"

        mgr = PluginManager(plugin_dir=None)
        mgr.register(P())
        plugins = mgr.plugins
        plugins.clear()
        # Original list must be unaffected
        assert len(mgr) == 1
