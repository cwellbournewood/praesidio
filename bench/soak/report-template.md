# Section gateway — soak report

> Copy this file to `bench/soak/results/<utc>/REPORT.md`, fill in the blanks,
> commit alongside the CSVs and the HTML report.

## Run metadata

| Field | Value |
|---|---|
| Date (UTC start) | `YYYY-MM-DDTHH:MM:SSZ` |
| Gateway version | `<git sha or release tag>` |
| Policy bundle digest | `<sha256 from /admin/policies/digest>` |
| Host / container shape | `<e.g. 4 vCPU / 8 GiB, single replica>` |
| Soak duration | `<e.g. 1h>` |
| Peak concurrent users | `<N>` |
| Target RPS | `<e.g. 100>` |
| Achieved mean RPS | `<filled from LOCUST_SUMMARY>` |
| Locust workers | `<n>` |
| Network round-trip (client → gateway) | `<ms>` |

## Headline numbers

| Metric | Value |
|---|---|
| Total requests | `<N>` |
| Failures | `<N>` (`<pct>` %) |
| p50 latency | `<ms>` |
| p95 latency | `<ms>` |
| p99 latency | `<ms>` |
| Max latency | `<ms>` |
| Audit-write error rate | `<pct>` |
| Circuit-breaker opens | `<count>` |
| Rate-limit blocks | `<count>` |

## Resource trace (paste Prometheus snapshots)

> Use the queries from [prometheus-queries.md](prometheus-queries.md).

* Gateway CPU (cores) over time — `<screenshot/link>`
* Gateway RSS (MiB) over time — `<screenshot/link>`
* Audit queue depth — `<screenshot/link>`
* Upstream p95 by provider — `<screenshot/link>`

## Per-scenario stats (Locust CSV)

| Scenario | reqs | fails | p50 ms | p95 ms | p99 ms | RPS |
|---|---:|---:|---:|---:|---:|---:|
| `POST /v1/chat/completions [short]` | | | | | | |
| `POST /v1/chat/completions [long]` | | | | | | |
| `POST /v1/chat/completions [stream]` | | | | | | |

## Observations

* _What surprised you?_
* _Any regression vs the previous soak?_
* _Where did the system run out of headroom first (CPU / RSS / DB)?_

## Follow-ups

| # | Issue | Owner | Priority |
|---:|---|---|---|
| 1 | | | |

## Sign-off

| Role | Name | Date |
|---|---|---|
| Soak run by | | |
| Reviewed by (SRE) | | |
| Reviewed by (Eng) | | |
