-- Section Gateway — vector store + per-document ACL.
--
-- Adds two tables used by the vector-store connectors:
--
--   vector_documents  — sanitised document text + embedding (pgvector).
--   documents_acl     — per-document read grants (principal or group).
--
-- Idempotent (IF NOT EXISTS everywhere). Safe to replay on the same volume.
--
-- The pgvector extension is required for the ``embedding`` column. If it
-- is unavailable in your Postgres distribution, install it with:
--   CREATE EXTENSION vector;
-- (Most managed Postgres providers ship it as an enabled extension.)
--
-- Embedding dimension is intentionally small (16) to match the default
-- ``_stub_embed`` used in the connector and tests. Production deployments
-- should ALTER this column to the model-specific dimensionality (e.g.
-- 1536 for OpenAI text-embedding-3-small, 768 for many BERT variants).

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- vector_documents
--   One row per sanitised document persisted via VectorConnector._persist.
--   The raw text is REPLACED with placeholders before insert — only the
--   sanitised form ever reaches this table. The reversal map lives in the
--   Redis vault, scoped by (tenant_id, document_id).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vector_documents (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    sanitised_text  TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding       vector(16),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vector_documents_tenant
    ON vector_documents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_vector_documents_metadata_gin
    ON vector_documents USING GIN (metadata jsonb_path_ops);

-- ANN index is created post-load (data-size-dependent), but a hint:
--   CREATE INDEX ON vector_documents
--     USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- documents_acl
--   Per-document grants. A row grants read access either to a principal
--   OR to a group (exactly one of the two should be non-null per row).
--   Multiple rows per (tenant_id, document_id) compose as UNION.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents_acl (
    tenant_id    TEXT NOT NULL,
    document_id  TEXT NOT NULL,
    principal_id TEXT,
    group_name   TEXT,
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by   TEXT,
    CONSTRAINT documents_acl_grant_subject_chk
        CHECK (principal_id IS NOT NULL OR group_name IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_acl_principal
    ON documents_acl (tenant_id, document_id, principal_id)
    WHERE principal_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_acl_group
    ON documents_acl (tenant_id, document_id, group_name)
    WHERE group_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_acl_lookup
    ON documents_acl (tenant_id, document_id);

-- ---------------------------------------------------------------------------
-- Row-Level Security
--   Both tables enforce the same section.tenant_id session variable
--   contract as audit_events / lineage_nodes.
-- ---------------------------------------------------------------------------
ALTER TABLE vector_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents_acl    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS section_tenant_isolation ON vector_documents;
CREATE POLICY section_tenant_isolation ON vector_documents
    USING      (tenant_id = current_setting('section.tenant_id', true)
                OR current_setting('section.tenant_id', true) = '*')
    WITH CHECK (tenant_id = current_setting('section.tenant_id', true)
                OR current_setting('section.tenant_id', true) = '*');

DROP POLICY IF EXISTS section_tenant_isolation ON documents_acl;
CREATE POLICY section_tenant_isolation ON documents_acl
    USING      (tenant_id = current_setting('section.tenant_id', true)
                OR current_setting('section.tenant_id', true) = '*')
    WITH CHECK (tenant_id = current_setting('section.tenant_id', true)
                OR current_setting('section.tenant_id', true) = '*');
