# Runbook — PraesidioSlowBurn6h

**Severity**: ticket · **SLO**: `praesidio.chat.availability` · **Burn class**: slow

## What fired

Sustained 5xx error rate on `/v1/chat/completions` over both the last
6h and last 30m is burning the 30-day error budget at > 6× the
sustainable rate. At this pace the 30d budget is consumed in ~5 days.

This is a **ticket** — investigate within the working day. It is not a
page. If it escalates to fast-burn, the page-level alert
(`PraesidioFastBurn1h`) will fire automatically.

## Likely causes

1. **Gradual upstream degradation** — provider latency increasing,
   timeouts occasionally tripping.
2. **Resource pressure** — gateway pod approaching CPU / memory
   limits; check `kube_pod_container_resource_requests` vs actual.
3. **DLP regression** — a new detector or rule increased false-positive
   rate or added latency, indirectly causing timeouts.
4. **Connection-pool saturation** — Postgres or Redis pool too small
   for current traffic; queues building.

## Triage (within working hours)

1. Compare the last 6h error rate to the rolling 7d average in the
   *Praesidio · SLO* dashboard.
2. Check `request_duration_seconds_bucket` p95 / p99 — if rising
   alongside errors, the gateway is the bottleneck.
3. Check `audit_write_total{outcome="err"}` — non-zero indicates
   audit pressure.
4. Inspect recent policy bundle reloads via
   `/admin/policies/digest` — a new bundle may have introduced an
   expensive rule.

## Mitigation

| Cause | Action |
|---|---|
| Upstream latency | Lower the upstream timeout; surface a faster-fail to clients; queue an upstream-provider review |
| Resource pressure | Bump the HPA target; add a replica; review request body sizes |
| DLP regression | Roll back to the previous signed policy bundle; open an issue with the offending rule id |
| Pool saturation | Increase `PRAESIDIO_DB_POOL_SIZE` / `PRAESIDIO_REDIS_POOL_SIZE`; restart pods cleanly |

## When to escalate

- If the burn rate doubles within 1h → expect `PraesidioFastBurn1h` to
  fire; pre-empt by paging the on-call.
- If `PraesidioErrorBudgetExhausted` fires (the 30d window itself), the
  release-pause policy applies — see `docs/release-process.md`.

## Post-incident

- File a brief postmortem if the burn was caused by Praesidio itself
  (not a third-party upstream).
- Add or tighten an SLO dashboard panel if the failure mode wasn't
  visible at first glance.
