# 06 · Audit & Lineage

## Goals

1. A compliance officer can pull every interaction a given user had with any
   LLM in a date range, and reconstruct it down to the policy version that
   decided it.
2. An incident responder can answer "did sensitive data X reach a model?"
   in seconds.
3. The log itself must be tamper-evident — a malicious admin must not be
   able to silently rewrite history.

## Schema (Postgres)

```sql
-- One row per LLM interaction.
CREATE TABLE audit_events (
  id              UUID PRIMARY KEY,           -- UUIDv7 (sortable by time)
  tenant_id       TEXT NOT NULL,
  occurred_at     TIMESTAMPTZ NOT NULL,
  principal_id    TEXT,
  principal_groups TEXT[],
  source_ip       INET,
  route           TEXT,
  upstream        TEXT,                       -- 'openai/gpt-4o-mini'
  decision        TEXT NOT NULL,              -- allow|transform|block|error
  rule_id         TEXT,                       -- which rule fired
  policy_id       TEXT,
  policy_version  TEXT,
  bundle_digest   TEXT,                       -- sha256 of active bundle
  findings        JSONB,                      -- Finding[] without raw text
  transforms      JSONB,                      -- applied transforms summary
  request_digest  TEXT,                       -- sha256 of canonical sanitised request
  response_digest TEXT,                       -- sha256 of canonical restored response
  latency_ms      INTEGER,
  bytes_in        INTEGER,
  bytes_out       INTEGER,
  degraded        BOOLEAN DEFAULT FALSE,
  prev_hash       TEXT,                       -- previous row's chain hash (per tenant)
  chain_hash      TEXT NOT NULL,              -- sha256(prev_hash || canonical(row))
  signature       TEXT                        -- optional Ed25519 sig of chain_hash
);

CREATE INDEX ON audit_events (tenant_id, occurred_at DESC);
CREATE INDEX ON audit_events (tenant_id, principal_id, occurred_at DESC);
CREATE INDEX ON audit_events USING GIN (findings jsonb_path_ops);

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
```

A `lineage_edges` table records the DAG of derivations:

```sql
CREATE TABLE lineage_nodes (
  id          UUID PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  kind        TEXT NOT NULL,                  -- prompt|retrieval|tool|output|embedding|memory_write
  ref         TEXT NOT NULL,                  -- e.g. audit_event_id, vector_doc_id
  meta        JSONB
);

CREATE TABLE lineage_edges (
  parent_id   UUID REFERENCES lineage_nodes(id),
  child_id    UUID REFERENCES lineage_nodes(id),
  relation    TEXT,                           -- 'derived_from'|'retrieved_from'|'tool_output_of'
  PRIMARY KEY (parent_id, child_id)
);
```

## Hash chain

Each row's `chain_hash = sha256(prev_hash || canonical_json(row_minus_chain_hash))`
where `prev_hash` is the previous row's `chain_hash` for the same tenant.
The most recent `chain_hash` per tenant is periodically (configurable;
default every 5 min) published to:

- a second Postgres node (read replica), and optionally
- a transparency log (RFC 9162-style) for auditors who want third-party
  attestation.

Verifying the chain requires reading rows in order and recomputing — an
admin who deletes or edits a row breaks every downstream hash.

Signing is optional: if `PRAESIDIO_AUDIT_SIGNING_KEY` is set (Ed25519), each
batch's terminal `chain_hash` is signed; the public key is published.

## Export

- **Splunk HEC** sink (`POST /services/collector` with JSON)
- **Sentinel** sink (Log Analytics workspace via HTTP Data Collector API)
- **Elastic** sink (Bulk API)
- **S3 / GCS / Azure Blob** sink for long-term archival, parquet-encoded

All sinks receive sanitised events — raw matched text is never exported.

## Lineage reconstruction

The lineage tracker hooks the following events into the DAG:

| Event | Nodes created |
|---|---|
| Prompt arrived | `prompt` |
| RAG retrieval | `retrieval` ← `prompt`, plus `retrieval` ← each `embedding` chunk |
| Tool invocation | `tool` ← `prompt` |
| Model output | `output` ← `prompt` (+ `retrieval` if used) |
| Embedding write | `embedding` ← `prompt` |
| Memory write | `memory_write` ← `prompt` and/or `output` |

The UI's lineage view (see [design-system §9](../design-system.md#9-components-shadcn-style-primitives-in-servicesuicomponentsui))
renders this as an interactive force-directed graph, clicking any node
opens the corresponding audit event.

## Retention

Per-tenant retention policy:
```yaml
retention:
  default_days: 365
  high_severity_days: 2555     # 7 years for regulated tenants
  anonymise_after_days: 90     # PII fields scrubbed from non-essential audit rows
  delete_after_days: 2555
```

Honours GDPR Article 17 (right to erasure) via tenant-scoped subject deletion
RPC; the chain is preserved by replacing the subject's row payload with a
`tombstone` containing the original hash.
