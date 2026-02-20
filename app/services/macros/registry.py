"""
MacroRegistry — central store of all registered macro handlers.

Macros can be synchronous or async:
    sync:  def my_macro(params: MacroParams, ctx: MacroContext) -> str
    async: async def my_macro(params: MacroParams, ctx: MacroContext) -> str

Register with the decorator:
    @macro_registry.register("MYMACRO")
    async def my_macro(params, ctx):
        return "<b>Hello</b>"
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


# params dict passed to every macro handler
MacroParams = dict[str, str]
MacroHandler = Callable[..., str | Awaitable[str]]


class MacroRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, MacroHandler] = {}
        self._is_async: dict[str, bool] = {}

    # ---------------------------------------------------------------- register

    def register(self, name: str):
        """
        Decorator that registers a function as a macro handler.

        Usage::

            @macro_registry.register("DATE")
            def date_macro(params, ctx):
                return datetime.utcnow().strftime("%Y-%m-%d")
        """
        def decorator(fn: MacroHandler) -> MacroHandler:
            self._handlers[name.upper()] = fn
            self._is_async[name.upper()] = asyncio.iscoroutinefunction(fn)
            logger.debug("Registered macro: %s (async=%s)", name.upper(), self._is_async[name.upper()])
            return fn
        return decorator

    # ------------------------------------------------------------------ lookup

    def has(self, name: str) -> bool:
        return name.upper() in self._handlers

    async def call(self, name: str, params: MacroParams, ctx) -> str:
        """Invoke a registered macro handler (sync or async)."""
        handler = self._handlers.get(name.upper())
        if handler is None:
            return f'%{name}%'   # leave unknown macros intact

        try:
            if self._is_async[name.upper()]:
                return await handler(params, ctx)
            else:
                return handler(params, ctx)
        except Exception as exc:
            logger.exception("Macro %s raised an error", name)
            return f'<span class="macro-error">[Macro {name} error: {exc}]</span>'

    # ---------------------------------------------------------- introspection

    def registered_names(self) -> list[str]:
        return sorted(self._handlers.keys())


# Singleton shared across the application
macro_registry = MacroRegistry()
