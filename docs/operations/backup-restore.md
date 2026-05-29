# Backup & restore

Praesidio holds two pieces of durable state that must be backed up:

1. **Postgres** — audit chain, lineage graph, optional config. Loss
   means loss of compliance evidence; the system continues to operate
   but cannot prove anything that happened before the recovery point.
2. **Redis token vault** — the reversible mapping
   placeholder → ciphertext(real-value). Loss means every placeholder
   currently in flight (live LLM transactions, cached chunks) becomes
   unreversible. See [`disaster-recovery.md`](disaster-recovery.md) for
   the blast radius and the HSM/KMS migration path.

This document covers the day-to-day backup/restore mechanics. RPO/RTO
targets at the bottom.

## Postgres

### Daily logical backup

For installations without managed PITR (e.g. a single-node Postgres),
run a nightly logical dump and ship to object storage:

```bash
PGPASSWORD="$PG_PASS" pg_dump \
    -h "$PG_HOST" -U praesidio -d praesidio \
    --format=custom --compress=9 \
    --file="/backups/praesidio-$(date -u +%Y%m%dT%H%M%SZ).dump"

aws s3 cp /backups/praesidio-*.dump \
    s3://cwellbournewood-praesidio-backups/postgres/ \
    --sse aws:kms --sse-kms-key-id alias/praesidio-backups
```

Restore:

```bash
createdb -h "$PG_HOST" -U postgres praesidio_restored
pg_restore -h "$PG_HOST" -U postgres -d praesidio_restored \
    --jobs=4 --no-owner --no-privileges \
    praesidio-20260527T000000Z.dump

# Verify the audit chain integrity before swapping connections:
PRAESIDIO_GATEWAY=http://localhost:8080 \
PRAESIDIO_API_KEY=... \
    praesidio-audit verify --tenant '*' --since 1y
```

### PITR (recommended)

Use managed Postgres PITR (RDS, Cloud SQL, Azure Flexible Server) for
production. Set the binlog/WAL retention window to ≥ your incident
discovery SLA — 7 days is the project's recommended floor.

PITR restore steps are provider-specific; the key thing is the **audit
verify** step afterwards. A point-in-time restore that lands mid-write
can leave a torn-tail at the latest chain link; `praesidio-audit verify`
will report exactly which event in which tenant chain is the first
inconsistent one, and operators can either accept the truncation
(documented in your incident report) or step further back.

### Schema migrations on restore

The restored database always satisfies whatever Alembic revision the
binary you restore *with* expects. Run

```bash
PRAESIDIO_DATABASE_URL="postgresql+asyncpg://..." \
    alembic upgrade head
```

as the first action after restore, before pointing the gateway at the
restored database.

## Redis token vault

The vault is **encrypted at rest by Praesidio itself** (AES-256-GCM with
HKDF-derived per-tenant keys). Loss of the Redis data file is a service
incident; loss of `PRAESIDIO_VAULT_KEY` is the actual catastrophe.

### Snapshot policy

Two snapshot mechanisms operate in parallel in production:

| Mechanism | Cadence | RPO contribution |
|---|---|---|
| Redis AOF (`appendonly yes`, `appendfsync everysec`) | continuous | ≤ 1 s |
| `BGSAVE` RDB snapshot | every 5 min, shipped to S3 | ≤ 5 min |

Configure on a self-managed Redis:

```bash
redis-cli CONFIG SET appendonly yes
redis-cli CONFIG SET appendfsync everysec
redis-cli CONFIG SET save "300 1"
```

Managed Redis (ElastiCache, Memorystore, Azure Cache) — enable AOF and
automated snapshots in the console; copy snapshots to a separate region.

### Restore

```bash
# Stop the Redis instance, copy the AOF + RDB files into the data dir,
# then start. The AOF replay is automatic; verify with:
redis-cli -h "$REDIS_HOST" DBSIZE
redis-cli -h "$REDIS_HOST" --scan --pattern 'praesidio:tok:*' | wc -l
```

After restore, the vault key MUST match what was active when the data
was written. If it does not, the gateway logs `vault: decrypt failed`
on every detokenise call; rotate-back the key from your secrets store
or accept the loss and follow `disaster-recovery.md`.

## Helm chart values + policy bundle

These are checked into Git — your source-of-truth is your Git history,
not a separate backup. The signed OCI policy bundle published by
`scripts/policy_publish.sh` is also durable in GHCR.

## Recovery objectives

| Component | RPO target | RTO target |
|---|---|---|
| Postgres (audit chain) | 5 min (managed PITR) or 24h (logical only) | 30 min |
| Redis token vault | 1 s (AOF) | 5 min (warm replica) / 30 min (cold) |
| Gateway containers | 0 (stateless) | < 5 min (rolling restart) |
| Helm chart / config | 0 (Git) | minutes |

For SLA-critical deployments, run an explicit **DR drill** quarterly:
take a non-prod copy of prod data, run the restore procedure end-to-end,
issue a tokenisation request before restore, restore, issue the
detokenise after restore, and confirm the round-trip matches.
