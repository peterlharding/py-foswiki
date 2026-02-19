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


