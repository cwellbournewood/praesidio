# Alembic migrations — Praesidio gateway

This directory contains the canonical schema history for the gateway's
audit + lineage tables. Alembic is the source of truth for ongoing schema
changes in every environment (dev, test, staging, production).

The SQL file under `services/gateway/migrations/0001_init.sql` is kept
**only** for the Postgres container's `docker-entrypoint-initdb.d`
first-boot init (a different Postgres code path that only fires on a
brand-new data volume in `docker compose up`). It is a verbatim mirror of
the `0001_initial` Alembic revision below. Do not edit it directly — add
a new Alembic revision and, if needed, re-export the SQL with
`alembic upgrade --sql head > migrations/0001_init.sql`.

## Common commands

All commands are run from `services/gateway/`.

```bash
# Apply all pending migrations against the configured database.
alembic upgrade head

# Roll back the most recent migration.
alembic downgrade -1

# Generate a new revision skeleton.
alembic revision -m "add foo column to audit_events"

# Generate a revision by auto-diffing the ORM models against the live DB.
# Always review the result — autogenerate is a starting point, not gospel.
alembic revision --autogenerate -m "sync findings column type"

# Show the current revision recorded in the database.
alembic current

# Show migration history (newest first).
alembic history --verbose

# Dump SQL for review (no DB connection required).
alembic upgrade head --sql
```

## Database URL resolution

`alembic/env.py` resolves the connection URL in this order:

1. `-x url=postgresql://...` on the command line.
2. `PRAESIDIO_DATABASE_URL` env var.
3. `DATABASE_URL` env var.
4. The placeholder in `alembic.ini` (a local SQLite file).

Async driver suffixes (`+asyncpg`, `+aiosqlite`) are stripped automatically
so the gateway's runtime `DATABASE_URL` value can be reused verbatim.

## Container behaviour

The gateway Dockerfile runs `alembic upgrade head` at container start before
launching uvicorn. Set `PRAESIDIO_AUTO_MIGRATE=0` to skip (useful for
local debugging or when running migrations out-of-band from a `Job`).

## Helm

In Kubernetes the chart already ships a `pre-upgrade` Helm hook
(`Job/<rel>-migrate`) that previously applied the SQL files via `psql`.
That job is being migrated to invoke `alembic upgrade head` from inside
the gateway image — track via the chart's release notes.

## Authoring a new migration

1. Make your ORM change in `praesidio_gateway/audit/models.py`.
2. Run `alembic revision --autogenerate -m "describe change"`.
3. Open the generated file under `alembic/versions/`, **review** the
   `upgrade()` / `downgrade()` bodies, and add anything autogenerate
   missed (`CREATE INDEX CONCURRENTLY`, RLS policies, data backfills,
   etc.). Keep both directions reversible where possible.
4. Run `alembic upgrade head` against a local Postgres and a local SQLite
   to confirm both paths work; run `pytest tests/test_alembic.py` for the
   regression check.
5. Add a CHANGELOG entry.
