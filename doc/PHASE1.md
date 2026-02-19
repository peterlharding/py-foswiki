
## Phase 1 — What was built

### Architecture overview

```
app/
├── main.py              — FastAPI factory with lifespan, CORS, routers, health check
├── core/
│   ├── config.py        — pydantic-settings: DB URL, JWT secret, storage paths, CORS
│   ├── database.py      — async SQLAlchemy engine/session factory, get_db dependency
│   └── security.py      — bcrypt hashing, JWT create/decode, auth dependencies
├── models/              — 6 ORM tables (see below)
├── schemas/             — Pydantic v2 request/response models
├── services/            — Business logic layer (no HTTP concerns)
│   ├── users.py
│   ├── webs.py
│   ├── topics.py        — versioned saves, diff engine
│   ├── attachments.py   — streaming upload, filename sanitisation
│   └── acl.py           — permission evaluation with DENY-wins logic
└── routers/             — FastAPI route handlers
    ├── auth.py          — register, login, refresh, /me
    ├── webs.py          — web CRUD + ACL
    ├── topics.py        — topic CRUD + raw + history + diff + rename + ACL
    └── attachments.py   — upload, list, download, delete
```

### Database schema (6 tables, 1 Alembic migration)

`users` → `webs` → `topics` → `topic_versions` (append-only), `topic_meta`, `attachments`, `acl` (polymorphic on resource_type + resource_id)

### Key design choices

**Versioning is append-only** — every `PUT /topics/{name}` writes a new `topic_versions` row. Nothing is ever overwritten. Rendered HTML is cached on the version row and invalidated on the next save.

**Attachments** stream in 64 KB chunks to disk, enforce the configurable size limit mid-stream, and sanitise filenames against path traversal. Uploading the same filename to the same topic replaces the previous record (upsert).

**ACL** is evaluated as DENY-wins: explicit denies beat allows; admins bypass all checks; no rule defaults to allow-view, deny-everything-else.

**Diff** uses Python's `difflib.SequenceMatcher` and returns structured `[{type, lines}]` groups rather than raw unified diff text, which makes it easy for the frontend to render coloured diffs.

**Phase 2 rendering is wired in** — `POST /topics` and `PUT /topics` both run content through the full macro + WikiWord + Markdown pipeline and return rendered HTML alongside raw content.



