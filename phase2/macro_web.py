"""
Web and Topic list macros
-------------------------
%WEBLIST%                           — list all webs
%WEBLIST{format="$name" sep=", "}% — formatted web list

%TOPICLIST%                         — list topics in current web
%TOPICLIST{web="Main" format="$topic" sep="\n"}%

format tokens for WEBLIST:  $name  $url
format tokens for TOPICLIST: $topic $web $url $date $author
"""

from __future__ import annotations

from .registry import MacroRegistry
from .params import get_param


def register(registry: MacroRegistry) -> None:

    @registry.register("WEBLIST")
    async def weblist_macro(params: dict, ctx) -> str:
        fmt = get_param(params, "format", default='<a href="$url">$name</a>')
        sep = get_param(params, "separator", "sep", default="\n").replace(r"\n", "\n")
        include_pattern = get_param(params, "include", default="")
        exclude_pattern = get_param(params, "exclude", default="")

        webs = await _list_webs(ctx.db)
        rows = []
        for web in webs:
            name = web["name"]
            if include_pattern and include_pattern not in name:
                continue
            if exclude_pattern and exclude_pattern in name:
                continue
            url  = f"{ctx.base_url}/view/{name}/WebHome"
            row  = fmt.replace("$name", name).replace("$url", url)
            rows.append(row)

        return sep.join(rows)

    @registry.register("TOPICLIST")
    async def topiclist_macro(params: dict, ctx) -> str:
        web  = get_param(params, "web", default=ctx.web)
        fmt  = get_param(params, "format", default="$topic")
        sep  = get_param(params, "separator", "sep", default="\n").replace(r"\n", "\n")
        limit = int(get_param(params, "limit", default="100"))

        topics = await _list_topics(ctx.db, web, limit)
        rows = []
        for t in topics:
            name  = t["name"]
            url   = ctx.topic_url(web, name)
            date  = str(t.get("modified_at", ""))
            author = t.get("author", "")
            row = (
                fmt
                .replace("$topic", name)
                .replace("$web", web)
                .replace("$url", url)
                .replace("$date", date)
                .replace("$author", author)
            )
            rows.append(row)

        return sep.join(rows)


async def _list_webs(db) -> list[dict]:
    if db is None:
        return []
    try:
        from sqlalchemy import text
        result = await db.execute(text("SELECT name FROM webs ORDER BY name"))
        return [{"name": row[0]} for row in result]
    except Exception:
        return []


async def _list_topics(db, web: str, limit: int) -> list[dict]:
    if db is None:
        return []
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("""
                SELECT t.name,
                       MAX(tv.created_at) AS modified_at
                FROM topics t
                JOIN webs w ON w.id = t.web_id
                LEFT JOIN topic_versions tv ON tv.topic_id = t.id
                WHERE w.name = :web
                GROUP BY t.name
                ORDER BY t.name
                LIMIT :limit
            """),
            {"web": web, "limit": limit},
        )
        return [{"name": row[0], "modified_at": row[1]} for row in result]
    except Exception:
        return []
