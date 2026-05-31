# Soak-test Prometheus queries

These are the Prometheus / PromQL queries operators run during and after a
soak window to confirm the gateway is healthy and to fill in the
[report template](report-template.md). All metric names below are emitted
by `section_gateway.obs.metrics`.

## Health (overall)

```promql
# Throughput by route (5m rolling)
sum by (route) (rate(request_total[5m]))

# Error rate (5xx / total)
sum(rate(request_total{status=~"5.."}[5m]))
  / clamp_min(sum(rate(request_total[5m])), 1e-9)

# Section-decision breakdown (allow / transform / block / shadow)
sum by (decision) (rate(decision_total[5m]))
```

## Latency

```promql
# Gateway p95 latency (per route)
histogram_quantile(0.95,
  sum by (le, route) (rate(request_latency_seconds_bucket[5m]))
)

# Upstream p95 latency (per provider/model)
histogram_quantile(0.95,
  sum by (le, provider, model) (rate(upstream_latency_seconds_bucket[5m]))
)

# Detector p95 latency (per detector)
histogram_quantile(0.95,
  sum by (le, detector) (rate(detector_latency_seconds_bucket[5m]))
)
```

## Audit pipeline

```promql
# Audit write throughput by outcome (ok | err)
sum by (outcome) (rate(audit_write_total[5m]))

# Audit error fraction — should stay < 0.1 %
sum(rate(audit_write_total{outcome="err"}[5m]))
  / clamp_min(sum(rate(audit_write_total[5m])), 1e-9)
```

## Safety nets that should NOT fire during a clean soak

```promql
# Circuit breakers opening (per detector)
sum by (detector) (rate(detector_breaker_opens_total[5m]))

# Rate-limit blocks (per tenant / route)
sum by (tenant, route) (rate(rate_limit_blocked_total[5m]))
```

## Resource utilisation (cgroup / kube-state)

```promql
# Gateway container CPU (cores)
sum by (pod) (rate(container_cpu_usage_seconds_total{
  namespace="section", container="gateway"}[5m]))

# Gateway container RSS (MiB)
sum by (pod) (container_memory_working_set_bytes{
  namespace="section", container="gateway"}) / 1024 / 1024
```

## Goroutines-equivalent for Python: asyncio task count

The gateway publishes ``asyncio_pending_tasks`` (gauge, if the asyncio
metrics collector is enabled). Steady-state should be < 2× peak in-flight
requests. A sustained climb indicates a leak in a stream handler or a stuck
upstream connection.

```promql
max by (instance) (asyncio_pending_tasks)
```

## Alert thresholds (soak-validation gate)

| Metric | Threshold | Meaning |
|---|---|---|
| `request_total{status=~"5.."}` rate | > 0.1% over 10m | regression — fail soak |
| `audit_write_total{outcome="err"}` rate | > 0 sustained | audit subsystem broken |
| Gateway p95 (`/v1/chat/completions`) | > 200 ms over 10m | latency regression |
| `detector_breaker_opens_total` | any non-zero | a detector is unstable |
| Gateway RSS | > 1.5 GiB | possible leak — collect heap dump |
