"""
Topic metadata macros
---------------------
%FORMFIELD{"FieldName"}%                — value of a DataForm field on current topic
%FORMFIELD{"FieldName" topic="Web.T"}%  — field on another topic

%META{"topicinfo" format="..."}%        — topic metadata (version, author, date)
  tokens: $version $author $date $format

%REVINFO%                               — shorthand: "r$rev – $date – $author"
%REVINFO{format="$date" rev="3"}%      — specific revision info
"""

from __future__ import annotations

from datetime import datetime
from .registry import MacroRegistry
from .params import get_param


def register(registry: MacroRegistry) -> None:

    @registry.register("FORMFIELD")
    async def formfield_macro(params: dict, ctx) -> str:
        field_name = get_param(params, "_default", "name")
        target     = get_param(params, "topic", default="")
        default    = get_param(params, "default", default="")
        alt        = get_param(params, "alttext", default=default)

        if target:
            web, topic = target.split(".", 1) if "." in target else (ctx.web, target)
        else:
            web, topic = ctx.web, ctx.topic

        value = await _get_form_field(ctx.db, web, topic, field_name)
        return value if value is not None else alt

    @registry.register("META")
    async def meta_macro(params: dict, ctx) -> str:
        meta_type = get_param(params, "_default", "type", default="topicinfo")
        fmt = get_param(params, "format", default="$version")
        target = get_param(params, "topic", default="")

        if target:
            web, topic = target.split(".", 1) if "." in target else (ctx.web, target)
        else:
            web, topic = ctx.web, ctx.topic

        if meta_type.lower() == "topicinfo":
            info = await _get_topic_info(ctx.db, web, topic)
            if not info:
                return ""
            return _apply_meta_format(fmt, info)
        return ""

    @registry.register("REVINFO")
    async def revinfo_macro(params: dict, ctx) -> str:
        rev_num = get_param(params, "rev", default="")
        fmt = get_param(params, "format",
                        default="r$rev – $date – $wikiusername")

        info = await _get_topic_info(ctx.db, ctx.web, ctx.topic, rev_num or None)
        if not info:
            return ""
        return _apply_meta_format(fmt, info)


# --------------------------------------------------------------------------- helpers

async def _get_form_field(db, web: str, topic: str, field: str) -> str | None:
    if db is None:
        return None
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("""
                SELECT tm.value
                FROM topic_meta tm
                JOIN topics t ON t.id = tm.topic_id
                JOIN webs w ON w.id = t.web_id
                WHERE w.name = :web AND t.name = :topic AND tm.key = :key
                LIMIT 1
            """),
            {"web": web, "topic": topic, "key": field},
        )
        row = result.first()
        return row[0] if row else None
    except Exception:
        return None


async def _get_topic_info(db, web: str, topic: str, rev: str | None = None) -> dict | None:
    if db is None:
        return None
    try:
        from sqlalchemy import text
        if rev:
            q = """
                SELECT tv.version, tv.created_at, u.display_name, u.username
                FROM topic_versions tv
                JOIN topics t ON t.id = tv.topic_id
                JOIN webs w ON w.id = t.web_id
                LEFT JOIN users u ON u.id = tv.author_id
                WHERE w.name = :web AND t.name = :topic AND tv.version = :rev
                LIMIT 1
            """
            params = {"web": web, "topic": topic, "rev": int(rev)}
        else:
            q = """
                SELECT tv.version, tv.created_at, u.display_name, u.username
                FROM topic_versions tv
                JOIN topics t ON t.id = tv.topic_id
                JOIN webs w ON w.id = t.web_id
                LEFT JOIN users u ON u.id = tv.author_id
                WHERE w.name = :web AND t.name = :topic
                ORDER BY tv.version DESC LIMIT 1
            """
            params = {"web": web, "topic": topic}

        result = await db.execute(text(q), params)
        row = result.first()
        if not row:
            return None
        version, created_at, display_name, username = row
        return {
            "version":     version,
            "date":        created_at,
            "author":      username or "",
            "wikiusername": display_name or username or "",
        }
    except Exception:
        return None


def _apply_meta_format(fmt: str, info: dict) -> str:
    date = info.get("date")
    date_str = date.strftime("%Y-%m-%d") if isinstance(date, datetime) else str(date or "")
    result = fmt
    result = result.replace("$rev",          str(info.get("version", "")))
    result = result.replace("$date",         date_str)
    result = result.replace("$author",       info.get("author", ""))
    result = result.replace("$wikiusername", info.get("wikiusername", ""))
    result = result.replace("$version",      str(info.get("version", "")))
    return result
