"""
Date/Time macros
----------------
%DATE%                  — current date (server local time)  →  2025-02-19
%GMTIME%                — UTC timestamp                     →  2025-02-19T12:34:56Z
%GMTIME{"$day $mon $year"}%  — formatted UTC time
%SERVERTIME%            — server local timestamp
%SERVERTIME{"$hour:$min"}%   — formatted local time

Format tokens (Foswiki-compatible):
  $seconds $minutes $hours  $day $wday $wdayname
  $month $mon $mo $year $ye $epoch  $tz $iso
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone

from .registry import MacroRegistry
from .params import get_param

_FORMAT_TOKENS = {
    "$seconds": lambda dt: f"{dt.second:02d}",
    "$minutes": lambda dt: f"{dt.minute:02d}",
    "$hours":   lambda dt: f"{dt.hour:02d}",
    "$day":     lambda dt: f"{dt.day:02d}",
    "$wday":    lambda dt: str(dt.weekday()),
    "$wdayname":lambda dt: calendar.day_name[dt.weekday()],
    "$month":   lambda dt: f"{dt.month:02d}",
    "$mon":     lambda dt: dt.strftime("%b"),
    "$mo":      lambda dt: f"{dt.month:02d}",
    "$year":    lambda dt: str(dt.year),
    "$ye":      lambda dt: dt.strftime("%y"),
    "$epoch":   lambda dt: str(int(dt.timestamp())),
    "$tz":      lambda dt: dt.strftime("%Z") or "UTC",
    "$iso":     lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
}

_DEFAULT_FMT = "%Y-%m-%d"
_DEFAULT_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _apply_format(fmt: str, dt: datetime) -> str:
    """Replace $token placeholders with dt values."""
    result = fmt
    for token, fn in _FORMAT_TOKENS.items():
        if token in result:
            result = result.replace(token, fn(dt))
    return result


def register(registry: MacroRegistry) -> None:

    @registry.register("DATE")
    def date_macro(params, ctx):
        """Current date in YYYY-MM-DD format."""
        now = datetime.now()
        fmt = get_param(params, "format", "_default")
        if fmt:
            return _apply_format(fmt, now)
        return now.strftime(_DEFAULT_FMT)

    @registry.register("GMTIME")
    def gmtime_macro(params, ctx):
        """UTC timestamp, optionally formatted."""
        now = datetime.now(tz=timezone.utc)
        fmt = get_param(params, "format", "_default")
        if fmt:
            return _apply_format(fmt, now)
        return now.strftime(_DEFAULT_TS_FMT)

    @registry.register("SERVERTIME")
    def servertime_macro(params, ctx):
        """Local server timestamp, optionally formatted."""
        now = datetime.now()
        fmt = get_param(params, "format", "_default")
        if fmt:
            return _apply_format(fmt, now)
        return now.strftime(_DEFAULT_TS_FMT)
