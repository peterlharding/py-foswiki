"""
Macro subsystem — public API.
"""

from .registry import MacroRegistry, macro_registry
from .engine import MacroEngine
from .context import MacroContext
from .builtins import register_all_builtins

__all__ = [
    "MacroRegistry",
    "macro_registry",
    "MacroEngine",
    "MacroContext",
    "register_all_builtins",
]
