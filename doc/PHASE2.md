# Python Foswiki - Phase 2

## Architecture

The render pipeline follows this exact sequence:

```
raw TML/Markdown
      ↓ pre-render plugin hooks
      ↓ macro expansion  (%MACRO{params}%)
      ↓ bracket link conversion  [[Target][Label]]
      ↓ Markdown → HTML  (mistune)
      ↓ WikiWord auto-linking  (on rendered HTML)
      ↓ post-render plugin hooks
   HTML output
```

WikiWord linking deliberately runs **after** Markdown — running it before would cause the injected `<a>` tags to get HTML-escaped by the Markdown renderer.

--

### Files delivered (18 files)

**Core infrastructure:**

- `macros/params.py` — parser for `key="value"`, `'single'`, positional, and flag params
- `macros/registry.py` — singleton handler store supporting both sync and async macros
- `macros/engine.py` — multi-pass expansion loop with depth guard (stops at 20 passes)
- `macros/context.py` — `MacroContext` dataclass carrying web, topic, user, DB session, search service through the pipeline
- `renderer.py` — `RenderPipeline` orchestrating all 6 stages

**Built-in macros (10 modules, ~30 macros):**

- `macro_date.py` — `%DATE%`, `%GMTIME%`, `%SERVERTIME%` with `$year/$month/$day` format tokens
- `macro_userinfo.py` — `%WIKINAME%`, `%USERNAME%`, `%USERINFO%`, `%GROUPS%`, `%ISMEMBER%`
- `macro_search.py` — `%SEARCH%` with text/regex/query types, `$topic/$summary/$date/$author` format tokens, nonoise mode
- `macro_include.py` — `%INCLUDE%` with named sections (`%STARTSECTION%/%ENDSECTION%`), raw mode, depth guard
- `macro_toc.py` — `%TOC%` scanning both Markdown ATX headings and TWiki `---+` headings
- `macro_color.py` — all 16 named colors + `%ENDCOLOR%`, `%IF%` with context/istopic/string conditions
- `macro_web.py` — `%WEBLIST%`, `%TOPICLIST%` with format tokens and DB queries
- `macro_topic.py` — `%FORMFIELD%`, `%META%`, `%REVINFO%` pulling structured metadata from DB
- `macro_format.py` — `%FORMATLIST%`, `%NOP%`, `%BR%`, `%NBSP%`, `%VBAR%`, `%BULLET%`

**WikiWord linker:**

- `wikiword/linker.py` — CamelCase detection, `Web.Topic` qualified links, `!Escape` suppression, skip regions (backtick code, existing anchors, URLs)
- `wikiword/html_linker.py` — post-Markdown HTML-aware linker that preserves existing `<a>`, `<code>`, `<pre>` tags

**Tests:** 78 tests covering every component in isolation and end-to-end.

---

## Key design decisions

`MacroContext` carries a `_render_fn` back-reference so `%INCLUDE%` can render included topics through the full pipeline without circular imports. Adding a new macro is a single decorated function — `@macro_registry.register("MYMACRO")`. The `SEARCH` macro expects an injected `search_service` so you can swap between PostgreSQL FTS and Meilisearch without touching macro code.


