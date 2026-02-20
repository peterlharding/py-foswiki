#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""Shared Jinja2 template engine instance."""
# -----------------------------------------------------------------------------

import os
from fastapi.templating import Jinja2Templates

_here = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(_here, "templates"))
