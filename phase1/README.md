
```sql

-- Organizational hierarchy
CREATE TABLE webs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    parent_id   UUID REFERENCES webs(id),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Topics (wiki pages)
CREATE TABLE topics (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    web_id      UUID REFERENCES webs(id) NOT NULL,
    name        TEXT NOT NULL,                      -- WikiWord or slug
    created_by  UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(web_id, name)
);

-- Versioned content (append-only)
CREATE TABLE topic_versions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id    UUID REFERENCES topics(id) NOT NULL,
    version     INTEGER NOT NULL,
    content     TEXT NOT NULL,                      -- Raw TML/Markdown
    rendered    TEXT,                               -- Cached HTML
    author_id   UUID REFERENCES users(id),
    comment     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(topic_id, version)
);

-- Structured metadata / DataForms equivalent
CREATE TABLE topic_meta (
    topic_id    UUID REFERENCES topics(id),
    key         TEXT NOT NULL,
    value       TEXT,
    PRIMARY KEY (topic_id, key)
);

-- Form schemas
CREATE TABLE form_schemas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    web_id      UUID REFERENCES webs(id),
    name        TEXT NOT NULL,
    fields      JSONB NOT NULL    -- [{name, type, options, required}]
);

-- Attachments
CREATE TABLE attachments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id    UUID REFERENCES topics(id),
    filename    TEXT NOT NULL,
    size        BIGINT,
    content_type TEXT,
    storage_path TEXT NOT NULL,
    uploaded_by UUID REFERENCES users(id),
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Access control
CREATE TABLE acl (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_type TEXT NOT NULL,     -- 'web' or 'topic'
    resource_id UUID NOT NULL,
    principal   TEXT NOT NULL,       -- user ID, group name, or '*'
    permission  TEXT NOT NULL,       -- 'view', 'edit', 'admin'
    allow       BOOLEAN NOT NULL DEFAULT TRUE
);
```

### FastAPI App Structure
```
pyfoswiki/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   │   ├── web.py
│   │   ├── topic.py
│   │   ├── user.py
│   │   └── attachment.py
│   ├── routers/
│   │   ├── webs.py          # CRUD for webs
│   │   ├── topics.py        # view, edit, save, history, diff
│   │   ├── search.py        # full-text + structured search
│   │   ├── attachments.py   # file upload/download
│   │   ├── forms.py         # DataForm schema management
│   │   └── auth.py
│   ├── services/
│   │   ├── renderer.py      # Markdown + macro expansion pipeline
│   │   ├── macros/          # Macro plugin system
│   │   │   ├── base.py
│   │   │   ├── search_macro.py
│   │   │   ├── userinfo_macro.py
│   │   │   └── formfield_macro.py
│   │   ├── versioning.py    # Topic version management
│   │   ├── acl.py           # Permission checking
│   │   └── search.py        # Search engine integration
│   └── plugins/             # Extension hooks (like Foswiki plugins)
│       ├── base.py
│       └── notification.py
├── frontend/                # React app
├── docker-compose.yml
└── tests/
```


## Renderer / Macro Engine

This is the heart of Foswiki.

In Python:

```
import re

from typing import Callable

class MacroEngine:
    """Processes %MACRO{param="value"}% syntax before Markdown rendering."""
    
    def __init__(self):
        self._macros: dict[str, Callable] = {}

    def register(self, name: str):
        def decorator(fn):
            self._macros[name] = fn
            return fn
        return decorator

    def expand(self, text: str, context: dict) -> str:
        """Recursively expand all macros in text."""
        pattern = re.compile(r'%([A-Z_]+)(?:\{([^}]*)\})?%')
        
        def replace(match):
            name = match.group(1)
            raw_params = match.group(2) or ""
            params = self._parse_params(raw_params)
            if name in self._macros:
                return self._macros[name](params, context)
            return match.group(0)  # leave unknown macros intact
        
        # Expand iteratively (macros can produce other macros)
        prev = None
        while prev != text:
            prev = text
            text = pattern.sub(replace, text)
        return text

    def _parse_params(self, raw: str) -> dict:
        # Parse key="value" pairs
        return dict(re.findall(r'(\w+)="([^"]*)"', raw))

# Usage
engine = MacroEngine()

@engine.register("SEARCH")
def search_macro(params: dict, context: dict) -> str:
    query = params.get("search", "")
    # ... run DB query and format results as HTML/TML
    return f"<div class='search-results'>...</div>"

@engine.register("USERINFO")
def userinfo_macro(params: dict, context: dict) -> str:
    user = context.get("current_user")
    field = params.get("format", "name")
    return getattr(user, field, "")
```


## Topic Render Pipeline

```
async def render_topic(topic_id: UUID, context: dict) -> str:
    version = await get_latest_version(topic_id)
    
    # 1. Run pre-render plugin hooks
    text = await plugin_manager.pre_render(version.content, context)
    
    # 2. Expand macros
    text = macro_engine.expand(text, context)
    
    # 3. Convert WikiWords to links
    text = wikiword_linker.process(text, context["web"])
    
    # 4. Render Markdown/TML to HTML
    html = markdown_renderer.render(text)
    
    # 5. Run post-render plugin hooks
    html = await plugin_manager.post_render(html, context)
    
    # 6. Cache the result
    await cache.set(f"rendered:{topic_id}", html, ttl=300)
    
    return html
```





## Plugin System — Simple hook-based architecture


```
class PluginBase:
    async def pre_render(self, text: str, context: dict) -> str:
        return text
    
    async def post_render(self, html: str, context: dict) -> str:
        return html
    
    async def on_save(self, topic: Topic, version: TopicVersion) -> None:
        pass
    
    async def on_attach(self, topic: Topic, attachment: Attachment) -> None:
        pass
```

### Key API Endpoints
```
GET    /v1/webs                          List webs
POST   /v1/webs                          Create web

GET    /v1/webs/{web}/topics             List topics in web
POST   /v1/webs/{web}/topics             Create topic

GET    /v1/webs/{web}/topics/{topic}     View topic (renders HTML)
GET    /v1/webs/{web}/topics/{topic}/raw Raw TML/Markdown source
PUT    /v1/webs/{web}/topics/{topic}     Save topic
DELETE /v1/webs/{web}/topics/{topic}     Delete topic

GET    /v1/webs/{web}/topics/{topic}/history         Version list
GET    /v1/webs/{web}/topics/{topic}/history/{ver}   Specific version
GET    /v1/webs/{web}/topics/{topic}/diff/{v1}/{v2}  Diff two versions

POST   /v1/webs/{web}/topics/{topic}/attachments     Upload file
GET    /v1/webs/{web}/topics/{topic}/attachments/{f} Download file

GET    /v1/search?q=...&web=...&type=...  Full-text search

GET    /v1/webs/{web}/topics/{topic}/acl  Get permissions
PUT    /v1/webs/{web}/topics/{topic}/acl  Set permissions
```




# Phased Build Approach

* Phase 1 — Core Wiki — Webs, topics, versioned editing, Markdown rendering, basic auth, file attachments
* Phase 2 — Macro Engine — %SEARCH%, %INCLUDE%, %TOC%, %USERINFO%, WikiWord auto-linking
* Phase 3 — DataForms — Form schema definition, structured field metadata attached to topics, form-based topic creation
* Phase 4 — Access Control — Per-web and per-topic ACLs, group support, LDAP integration
* Phase 5 — Plugin System — Hook architecture, email notifications, RSS/Atom feeds, REST extension points
* Phase 6 — Admin UI — Site config, user management, plugin management, statistics



