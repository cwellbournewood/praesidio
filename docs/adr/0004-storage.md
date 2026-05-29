# ADR-0004 · Storage choices

Date: 2026-05-27 · Status: Accepted

## Context

We need: (a) a durable, queryable audit/lineage store; (b) an ephemeral,
high-throughput KV for the token vault and policy cache; (c) optionally,
high-cardinality event analytics.

## Decision

- **Postgres** (with `pgcrypto`, optionally TimescaleDB) for audit + lineage.
  Reasons: rich queries on JSONB findings; widely operated; row-level
  security for multi-tenant; native LISTEN/NOTIFY for lineage events.
- **Redis** for token vault and policy decision cache. Reasons: AES-GCM
  cipher fits naturally in opaque strings; TTLs are native; sub-ms reads.
- **Optional ClickHouse** sink for tenants needing >10k events/s analytics
  (documented in `docs/architecture/06-audit-lineage.md`); not required for
  MVP.

## Consequences

- ➕ Boring infrastructure choices, deployable everywhere.
- ➕ Postgres + Redis is the lowest-friction enterprise install.
- ➖ Very high write rates may require sharding Postgres or moving to
  ClickHouse — addressed in the optional sink path.
