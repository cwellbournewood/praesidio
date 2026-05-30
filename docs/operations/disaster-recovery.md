# Disaster recovery

This document covers the catastrophic-loss scenarios that
[`backup-restore.md`](backup-restore.md) does not — the cases where
straightforward restore is not possible.

## Scenario 1 — Vault key (`SECTION_VAULT_KEY`) is lost

The token vault stores `placeholder → AES-256-GCM(real-value)` mappings
keyed by `SECTION_VAULT_KEY` (per-tenant HKDF). Loss of the master key
means every entry in the vault is **mathematically unreversible**. The
operational impact:

* In-flight LLM responses containing placeholders cannot be restored.
  Users see literal `<EMAIL_AB23>` tokens in chat output.
* The `/admin/detokenise` endpoint returns "vault: decrypt failed" for
  every previously-vaulted token.
* New traffic recovers immediately — a fresh tokenisation cycle uses
  whatever key is configured.

**Mitigation (before the loss):**

* Store `SECTION_VAULT_KEY` in an HSM-backed KMS (AWS KMS with
  HSM-backed keys, GCP Cloud HSM, Azure Dedicated HSM). The chart
  references it by `secrets.kmsRef` for auditability.
* Replicate the key across at least two regions in the same KMS.
* Hold an offline-encrypted copy at a custodial 3rd party (Iron Mountain
  / equivalent) sealed under Shamir 3-of-5.

**Response (after the loss):**

1. **Stop accepting new traffic** by scaling the gateway to zero or
   flipping the upstream LB to a maintenance page. This prevents users
   from generating placeholders that will be born unreversible if the
   key is recovered to a different value.
2. **Attempt KMS-side key restore** (region failover, HSM backup).
3. If restore is impossible:
   - Generate a new vault key and rotate it in (see "Rotation procedure"
     below).
   - **Purge the vault**: `redis-cli -h $R DEL $(redis-cli -h $R --scan
     --pattern 'section:tok:*')`. Any cached placeholder lookups will
     fail loudly rather than returning ciphertext under the old key.
   - Mark the recovery point in the audit chain by emitting an
     `audit.event` with `decision=admin` and `reason="vault key rotated
     after loss"`. Compliance teams will use this as the boundary
     between trustable and untrustable past responses.
4. Communicate to affected tenants: which `request_id` ranges contained
   placeholders that can no longer be reversed.

## Scenario 2 — Postgres audit chain corruption / torn-tail after restore

After a PITR restore that lands mid-write, the latest few chain links
in some tenant may not validate. `section-audit verify` will report
the first broken link.

**Response:**

1. Truncate forward of the broken link in the affected tenant:
   `DELETE FROM audit_events WHERE tenant_id=... AND occurred_at > ...`.
2. Re-run `section-audit verify --tenant <id>`. Expect a clean chain.
3. Document the truncation in your incident report with the lost
   `request_id` range — those events did exist but the chain proof was
   torn.

## Scenario 3 — Region failure

Section has **no built-in cross-region replication**. The standard
pattern:

* Active-active Postgres logical replication (or RDS cross-region
  read-replica + promotion).
* Redis cross-region replication (ElastiCache Global Datastore /
  Memorystore replicas).
* Gateway runs in both regions, fronted by GeoDNS / Anycast.
* Vault key is **the same value** in both regions, distributed via the
  KMS replication mechanism. Do not let the two regions diverge —
  placeholders born in region A must be reversible in region B.

When the primary region is lost, promote the replica Postgres + Redis,
flip DNS, and run `section-audit verify --tenant '*'` end-to-end before
allowing traffic.

## Scenario 4 — Compromise (signed-bundle CA, container image, or vault key)

Treat as a security incident first, DR second.

1. **Rotate immediately** — the compromised secret, the OCI repository
   pull-token, or the cosign root-of-trust as applicable.
2. **Pull all in-flight signed bundles** that were signed under the
   compromised identity. Re-sign and re-publish.
3. **Re-verify all running pods** against the new signature. The chart
   exposes `policyBundle.signatureVerification: cosign` — pods refuse
   to load unverifiable bundles, which gives natural quarantine.
4. **Audit-chain forensics** — query for unusual `decision=allow`
   rows around the compromise window, paying attention to
   `principal_id`, `policy_version`, and `bundle_digest`. Any row whose
   `bundle_digest` does not match an audited published digest is
   suspect.
5. **Public disclosure** — see `SECURITY.md` for the 90-day window.

## Vault-key rotation procedure (planned, not emergency)

Section supports two-key rotation:

1. Stand up a second `SECTION_VAULT_KEY_NEXT` env var alongside the
   live one. The gateway encrypts new entries with `NEXT` and falls back
   to the legacy key on read.
2. Run for ≥ max vault TTL (default 1h) so the legacy-key entries age
   out naturally.
3. Promote `NEXT` to primary, drop the legacy.
4. Restart and verify.

> **Do not** rotate the vault key without this procedure. A naive
> rotation makes every existing placeholder unreversible (see
> Scenario 1).

## Drill schedule

| Drill | Frequency |
|---|---|
| Postgres restore from backup | quarterly |
| Redis AOF replay | quarterly |
| Vault-key rotation (planned) | bi-annually |
| Region failover | annually |
| Vault-key loss simulation (in non-prod) | annually |

Record drill outcomes in `docs/operations/dr-log.md` (created on first
drill). The log becomes evidence for SOC 2 CC7.5 and ISO 27001 A.17.1.3.
