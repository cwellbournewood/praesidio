# Section Grafana dashboards

Two dashboards plus provisioning manifests:

| File | Purpose |
|---|---|
| `dashboards/section-overview.json` | Throughput by route, decision distribution, DLP detector p50/p99, vault hit ratio, upstream latency by provider, error rate |
| `dashboards/section-compliance.json` | Per-tenant audit volume, false-positive rate by detector, retention status, hash-chain validity |
| `provisioning/datasources.yaml` | Prometheus + Loki datasource manifest |
| `provisioning/dashboards.yaml` | File-based dashboard provider |

## Metrics used

Emitted by the gateway per `docs/architecture/02-gateway.md`:

- `request_total{route,status,...}` — counter
- `decision_total{decision,tenant,...}` — counter; `decision ∈ {allow,transform,block,error}`
- `detector_latency_seconds_bucket{detector,le}` — histogram
- `detector_findings_total{detector}` — counter
- `detector_feedback_total{detector,label}` — counter (operator feedback)
- `vault_ops_total{op,result}` — counter; `op ∈ {lookup,store,delete}`; `result ∈ {hit,miss,error}`
- `upstream_latency_seconds_bucket{provider,le}` — histogram
- `section_audit_events_total{...}` — gauge
- `section_audit_oldest_event_timestamp_seconds` — gauge
- `section_audit_retention_days` — gauge
- `section_audit_chain_valid` — gauge (0 = broken, 1 = valid)

If your metric names differ, override via dashboard variables or edit the
JSON in place.

## How to import

### Via the Grafana UI

1. Dashboards -> Import -> Upload JSON file
2. Pick `section-overview.json` (then `section-compliance.json`)
3. Choose your Prometheus datasource when prompted

### Via provisioning (Helm)

If using the `grafana/grafana` chart:

```yaml
datasources:
  datasources.yaml:
    apiVersion: 1
    datasources:
      - name: Prometheus
        type: prometheus
        url: http://prometheus-server.monitoring.svc.cluster.local:9090
        isDefault: true

dashboardProviders:
  dashboardproviders.yaml:
    apiVersion: 1
    providers:
      - name: section
        folder: Section
        type: file
        options:
          path: /var/lib/grafana/dashboards/section

dashboardsConfigMaps:
  section: section-grafana-dashboards
```

Then create a ConfigMap from the dashboards directory:

```bash
kubectl -n monitoring create configmap section-grafana-dashboards \
  --from-file=deploy/grafana/dashboards/
```

### Via the manifests in `provisioning/`

For a self-hosted Grafana, drop `provisioning/datasources.yaml` at
`/etc/grafana/provisioning/datasources/` and `provisioning/dashboards.yaml`
at `/etc/grafana/provisioning/dashboards/`, then mount the
`dashboards/` directory at `/var/lib/grafana/dashboards/section/`.
