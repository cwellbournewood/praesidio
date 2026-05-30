# Observability stack

Section ships a turn-key local observability overlay: Tempo for
traces, Loki + Promtail for logs, Prometheus for metrics, and Grafana
pre-provisioned with the same dashboards used in production.

## One-liner

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.observability.yml \
  up --build
```

Open <http://localhost:3001> (admin / admin) and the "Section"
folder will contain the overview and compliance dashboards.

| Port | Service | Notes |
|---|---|---|
| 3001 | Grafana | admin/admin, anonymous viewer enabled |
| 9090 | Prometheus | scrapes gateway `/metrics` every 15s |
| 3200 | Tempo HTTP | trace query API |
| 4317 | Tempo OTLP gRPC | gateway exports here |
| 3100 | Loki | log ingest + query |

## How the overlay layers in

`docker-compose.observability.yml` does **not** modify the root
compose definitions destructively. It:

1. Adds Prometheus / Tempo / Loki / Promtail / Grafana services.
2. Layers an `OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317` env onto
   the `gateway` service — only when this overlay is active.
3. Tags `gateway` and `ui` with Docker labels (`logging=promtail`)
   that promtail's service discovery uses to scrape stdout.

So the **root** compose stack stays exactly as documented in the
quickstart: nothing about it changes when you don't use this overlay.

## What you get

- **Metrics**: Prometheus scrapes `gateway:8080/metrics`. The
  `Section Overview` dashboard renders request rate, p50/p95/p99
  latency, decision mix (allow/transform/block), and DLP detector
  hit rates.
- **Traces**: Each request through the gateway emits an OTLP trace
  (HTTP -> auth -> policy eval -> DLP scan -> vault -> upstream).
  Look at the `Tempo` datasource in Grafana, or jump from a log line
  using the `trace_id=` derived field.
- **Logs**: Promtail tails Docker stdout for any container labelled
  `logging=promtail`. Filter by `{job="section-gateway"}` in the
  Grafana Explore view.

## SLO & burn-rate alerting

The dashboard `Section — SLO & burn rate`
(`deploy/grafana/dashboards/section-slo.json`) renders the 99.9 %
availability SLO for `/v1/chat/completions`: error-budget remaining over
30 days, plus the four burn-rate panels (fast 1h / 5m, slow 6h / 30m)
from the Google SRE multi-window multi-burn-rate model.

The matching Prometheus alert rules live in
`deploy/grafana/alerts/section-slo.yaml`:

| Alert | Class | Window pair | Burn rate | For |
|---|---|---|---|---|
| `SectionFastBurn1h` | page | 1h × 5m | > 14.4 × | 2m |
| `SectionSlowBurn6h` | ticket | 6h × 30m | > 6 × | 15m |
| `SectionErrorBudgetExhausted` | ticket | 30d cumulative | > 0.1 % errors | 10m |

Both pair-alerts require **both** windows to trip before firing, which
suppresses pages from minute-long blips while still catching real
regressions within ~5 minutes.

To load the alerts into a vanilla Prometheus instance, mount
`section-slo.yaml` into `/etc/prometheus/rules/` and add
`rule_files: [/etc/prometheus/rules/*.yaml]` to your Prometheus config.
For Prometheus Operator, uncomment the `PrometheusRule` wrapper at the
bottom of the file and `kubectl apply` it.

## Production wiring

In production this overlay is **not** used. Instead:

- Run a real Prometheus / Tempo / Loki (or vendor equivalents:
  Datadog, New Relic, Grafana Cloud).
- Point the gateway at them via env (`OTEL_EXPORTER_OTLP_ENDPOINT`,
  `SECTION_LOG_FORMAT=json`).
- Enable the ServiceMonitor in the Helm chart
  (`metrics.serviceMonitor.enabled=true`) so prometheus-operator
  discovers gateway pods automatically.
- Use `deploy/grafana/dashboards/*.json` directly — the compose
  overlay mounts the same files, so dashboards stay in sync.

## Troubleshooting

- **Grafana shows no data**: confirm `gateway` is healthy
  (`docker compose ps`) and that `curl http://localhost:8080/metrics`
  returns Prometheus text. The scrape interval is 15s, so allow up
  to 30s for the first sample.
- **No traces in Tempo**: the OTLP exporter requires the
  `opentelemetry-sdk` install in the gateway image (already included).
  If you've overridden the gateway image, ensure the dependency is
  present and `OTEL_EXPORTER_OTLP_ENDPOINT` resolves from inside the
  container.
- **Promtail errors about docker.sock**: the overlay mounts the host
  Docker socket read-only. On Docker Desktop for Windows / macOS the
  socket lives at `/var/run/docker.sock` inside the VM and works
  unchanged.
