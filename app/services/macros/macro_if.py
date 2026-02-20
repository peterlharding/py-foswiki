"""
macro_if — %IF% macro registration.

The IF macro (and related condition helpers) are implemented in macro_color.py
alongside the color macros.  This module exists so builtins.py can import it
as a distinct module; it delegates registration to macro_color.
"""

from .registry import MacroRegistry


def register(registry: MacroRegistry) -> None:
    """No-op: IF is registered by macro_color.register()."""
    pass
