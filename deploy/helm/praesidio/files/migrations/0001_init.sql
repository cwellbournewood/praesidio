-- Praesidio Gateway — initial schema (audit + lineage).
-- Idempotent (uses IF NOT EXISTS) so Postgres' docker-entrypoint-initdb.d
-- can replay safely.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- audit_events
--   One row per LLM interaction (request/response). Hash-chained per tenant.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_events (
    id               UUID PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_id       TEXT NOT NULL,
    principal_id     TEXT,
    principal_groups TEXT[],
    source_ip        INET,
    route            TEXT,
    upstream         TEXT,
    decision         TEXT NOT NULL,
    rule_id          TEXT,
    rule_index       INTEGER,
    policy_id        TEXT,
    policy_version   TEXT,
    bundle_digest    TEXT,
    findings         JSONB,
    transforms       JSONB,
    request_digest   TEXT,
    response_digest  TEXT,
    latency_ms       INTEGER,
    bytes_in         INTEGER,
    bytes_out        INTEGER,
    degraded         BOOLEAN NOT NULL DEFAULT FALSE,
    mode             TEXT NOT NULL DEFAULT 'enforce',
    reason           TEXT,
    severity         TEXT,
    prev_hash        TEXT,
    chain_hash       TEXT NOT NULL,
    signature        TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_time
    ON audit_events (tenant_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_principal_time
    ON audit_events (tenant_id, principal_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_request_id
    ON audit_events (request_id);
CREATE INDEX IF NOT EXISTS idx_audit_findings_gin
    ON audit_events USING GIN (findings jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_audit_decision
    ON audit_events (tenant_id, decision, occurred_at DESC);

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;

-- Default RLS policy: app role must SET praesidio.tenant_id per session.
-- The bypass role (DB owner) is unrestricted.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema() AND tablename = 'audit_events'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON audit_events
            USING (
                tenant_id = current_setting('praesidio.tenant_id', true)
                OR current_setting('praesidio.tenant_id', true) = '*'
            );
    END IF;
END$$;

-- ---------------------------------------------------------------------------
-- lineage_nodes / lineage_edges
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lineage_nodes (
    id          UUID PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    request_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    ref         TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta        JSONB
);

CREATE INDEX IF NOT EXISTS idx_lineage_nodes_request
    ON lineage_nodes (tenant_id, request_id);
CREATE INDEX IF NOT EXISTS idx_lineage_nodes_kind
    ON lineage_nodes (tenant_id, kind);

ALTER TABLE lineage_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE lineage_nodes FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema() AND tablename = 'lineage_nodes'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON lineage_nodes
            USING (
                tenant_id = current_setting('praesidio.tenant_id', true)
                OR current_setting('praesidio.tenant_id', true) = '*'
            );
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS lineage_edges (
    parent_id  UUID NOT NULL REFERENCES lineage_nodes(id) ON DELETE CASCADE,
    child_id   UUID NOT NULL REFERENCES lineage_nodes(id) ON DELETE CASCADE,
    relation   TEXT NOT NULL,
    PRIMARY KEY (parent_id, child_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_lineage_edges_child ON lineage_edges (child_id);
