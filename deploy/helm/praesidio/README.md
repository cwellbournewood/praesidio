# Praesidio Helm chart

Production-shaped chart for the Praesidio AI Security Control Plane
(gateway + admin UI, with optional embedded Postgres / Redis for dev).

## TL;DR

```bash
helm repo add praesidio https://cwellbournewood.github.io/praesidio   # (when published)
helm install praesidio praesidio/praesidio \
  -n praesidio --create-namespace \
  -f my-values.yaml
```

Or from a local checkout:

```bash
cd deploy/helm/praesidio
helm dependency update          # no-op today; reserved for subcharts
helm lint .
helm template . | less          # eyeball the rendered manifests
helm install praesidio . -n praesidio --create-namespace -f my-values.yaml
```

## What's in the chart

| Resource | When created |
|---|---|
| `Deployment/<rel>-gateway` | always |
| `Service/<rel>-gateway` | always |
| `HorizontalPodAutoscaler/<rel>-gateway` | `autoscaling.gateway.enabled` |
| `PodDisruptionBudget/<rel>-gateway` | `podDisruptionBudget.gateway.enabled` |
| `NetworkPolicy/<rel>-gateway` | `networkPolicy.enabled` |
| `ServiceAccount/<rel>` | `serviceAccount.create` |
| `Deployment/<rel>-ui` + Service + PDB + NP | always (NP gated on `networkPolicy.enabled`) |
| `ConfigMap/<rel>-policies` | `policyBundle.source == configmap` |
| `Secret/<rel>-gateway` | `secrets.externalSecrets == false` |
| `ExternalSecret/<rel>-gateway` | `secrets.externalSecrets == true` |
| `StatefulSet/<rel>-postgres` + Service | `postgres.embedded` |
| `StatefulSet/<rel>-redis` + Service | `redis.embedded` |
| `Job/<rel>-migrate` (pre-upgrade hook) | `migrations.enabled` |
| `Ingress/<rel>` | `ingress.enabled` |
| `ServiceMonitor` | `metrics.serviceMonitor.enabled` |

## Values reference (highlights)

| Key | Default | Description |
|---|---|---|
| `image.gateway.repository` | `ghcr.io/praesidio/gateway` | Gateway image |
| `image.ui.repository` | `ghcr.io/praesidio/ui` | UI image |
| `replicas.gateway` | `3` | Used when HPA disabled |
| `autoscaling.gateway.enabled` | `true` | HPA on the gateway |
| `autoscaling.gateway.maxReplicas` | `50` | HPA ceiling |
| `gateway.failMode` | `closed` | `open` or `closed` — see arch docs |
| `gateway.upstreamFQDNs[]` | OpenAI/Anthropic | Allowed egress FQDNs (Cilium CNP recommended for FQDN enforcement) |
| `policyBundle.source` | `configmap` | `configmap` / `http` / `s3` / `git` |
| `policyBundle.signatureVerification` | `cosign` | `cosign` or `none` |
| `secrets.externalSecrets` | `true` | Use external-secrets-operator vs in-chart Secret |
| `secrets.kmsRef` | empty | Informational KMS key reference |
| `networkPolicy.enabled` | `true` | NetworkPolicies for gateway + UI |
| `postgres.embedded` | `false` | Dev/demo only |
| `redis.embedded` | `false` | Dev/demo only |
| `ingress.enabled` | `false` | Optional single ingress for gateway + UI |
| `metrics.serviceMonitor.enabled` | `false` | Requires prometheus-operator |

See `values.yaml` for the full set with inline documentation, and
`values.schema.json` for the JSON Schema applied at `helm install`.

## Upgrade notes

* Migrations are run as a `pre-upgrade` Helm hook via `Job/<rel>-migrate`.
  The Job applies SQL files from `files/migrations/*.sql`. To disable, set
  `migrations.enabled=false` and run migrations out-of-band.
* Bundle changes (under `files/policies/`) trigger a rolling restart of
  the gateway via a checksum annotation.

## Production deployment

A canonical production overlay lives at `values.production.yaml`. Layer
it on top of `values.yaml`:

```bash
helm upgrade --install praesidio deploy/helm/praesidio \
    -n praesidio --create-namespace \
    -f deploy/helm/praesidio/values.production.yaml \
    -f my-site-values.yaml
```

Pair it with one of the three secrets walkthroughs:

* [`docs/operations/secrets-aws-secrets-manager.md`](../../../docs/operations/secrets-aws-secrets-manager.md)
  — AWS Secrets Manager + External Secrets Operator (recommended on EKS).
* [`docs/operations/secrets-vault.md`](../../../docs/operations/secrets-vault.md)
  — HashiCorp Vault KV v2 + External Secrets Operator.
* [`docs/operations/secrets-sealed-secrets.md`](../../../docs/operations/secrets-sealed-secrets.md)
  — Bitnami Sealed Secrets (Git-of-truth, no external KMS required).

## Production checklist

- [ ] `secrets.externalSecrets: true` with a real `secretStore`.
- [ ] `postgres.embedded: false`; point `postgres.externalDSN` at managed Postgres.
- [ ] `redis.embedded: false`; point `redis.externalURL` at managed Redis.
- [ ] `policyBundle.source` is `s3` or `git`, with `signatureVerification: cosign`.
- [ ] `ingress.tls` configured.
- [ ] `serviceAccount.annotations` set for IRSA / Workload Identity.
- [ ] `networkPolicy.enabled: true` and your CNI enforces FQDN egress (Cilium CNP recommended).
- [ ] HPA `maxReplicas` and PDB `minAvailable` sized for your traffic.

## CI

`helm lint` and `helm template` should both succeed on PRs that touch
`deploy/helm/**`. See `.github/workflows/helm.yml`.
