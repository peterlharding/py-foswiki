"""
Built-in macro registrations.
Call register_all_builtins() once at application startup.
"""

from .registry import macro_registry
from . import (
    macro_date,
    macro_userinfo,
    macro_search,
    macro_include,
    macro_toc,
    macro_color,
    macro_web,
    macro_topic,
    macro_if,
    macro_format,
)


def register_all_builtins() -> None:
    """Register every built-in macro with the shared registry."""
    macro_date.register(macro_registry)
    macro_userinfo.register(macro_registry)
    macro_search.register(macro_registry)
    macro_include.register(macro_registry)
    macro_toc.register(macro_registry)
    macro_color.register(macro_registry)
    macro_web.register(macro_registry)
    macro_topic.register(macro_registry)
    macro_if.register(macro_registry)
    macro_format.register(macro_registry)
