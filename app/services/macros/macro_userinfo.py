"""
User information macros
-----------------------
%WIKINAME%              — wiki name of current user  (e.g. "JohnDoe")
%USERNAME%              — login name                 (e.g. "jdoe")
%USERINFO%              — display name (default)
%USERINFO{"jdoe" format="$emails"}%  — specific field for named user
%GROUPS%                — comma-separated list of current user's groups
%ISMEMBER{"Admins"}%    — "1" if current user is in that group, else ""

USERINFO format tokens:
  $username   $wikiname   $emails   $groups   $displayname
"""

from __future__ import annotations

from .registry import MacroRegistry
from .params import get_param


def register(registry: MacroRegistry) -> None:

    @registry.register("WIKINAME")
    def wikiname_macro(params, ctx):
        if ctx.current_user:
            return ctx.current_user.get("wiki_name") or ctx.current_user.get("username", "Guest")
        return "Guest"

    @registry.register("USERNAME")
    def username_macro(params, ctx):
        if ctx.current_user:
            return ctx.current_user.get("username", "guest")
        return "guest"

    @registry.register("USERINFO")
    async def userinfo_macro(params, ctx):
        """
        Return formatted info about a user.

        %USERINFO%                         → display name of current user
        %USERINFO{"jdoe"}%                 → display name of jdoe
        %USERINFO{"jdoe" format="$emails"}% → email of jdoe
        """
        target_username = get_param(params, "_default", "username")
        fmt = get_param(params, "format", default="$displayname")

        if target_username and ctx.db:
            # Async DB lookup for a named user
            user = await _fetch_user(ctx.db, target_username)
        else:
            user = ctx.current_user

        if not user:
            return "(unknown user)"

        return _format_user(fmt, user)

    @registry.register("GROUPS")
    def groups_macro(params, ctx):
        groups = ctx.user_groups()
        return ", ".join(groups) if groups else ""

    @registry.register("ISMEMBER")
    def ismember_macro(params, ctx):
        group = get_param(params, "_default", "group")
        return "1" if group in ctx.user_groups() else ""


async def _fetch_user(db, username: str) -> dict | None:
    """Look up a user by username. Returns None if not found."""
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT id, username, display_name, email FROM users WHERE username = :u LIMIT 1"),
            {"u": username},
        )
        row = result.mappings().first()
        if row:
            return dict(row)
    except Exception:
        pass
    return None


def _format_user(fmt: str, user: dict) -> str:
    replacements = {
        "$username":    user.get("username", ""),
        "$wikiname":    user.get("wiki_name") or user.get("username", ""),
        "$emails":      user.get("email", ""),
        "$email":       user.get("email", ""),
        "$displayname": user.get("display_name") or user.get("username", ""),
        "$groups":      ", ".join(user.get("groups", [])),
    }
    result = fmt
    for token, value in replacements.items():
        result = result.replace(token, value)
    return result
