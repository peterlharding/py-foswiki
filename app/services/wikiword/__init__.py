"""
WikiWord auto-linker subsystem.
"""

from .linker import WikiWordLinker
from . import html_linker  # registers process_html onto WikiWordLinker

__all__ = ["WikiWordLinker"]
