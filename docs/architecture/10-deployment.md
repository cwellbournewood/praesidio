# 10 · Deployment & Operations

## Deployment modes

| Mode | Description |
|---|---|
| **Docker Compose** | `make dev` — single host, gateway + ui + postgres + redis + (optional) ollama |
| **Kubernetes (Helm)** | `deploy/helm/praesidio` — HA, HPA, NetworkPolicies, PDBs |
| **Air-gapped** | Helm chart with all images bundled; policy bundle delivered via offline media; local models via Ollama or vLLM |
| **Hosted (SaaS)** | Multi-tenant gateway behind a managed LB; per-tenant policy bundles; KMS-backed keys |
| **Hybrid** | Control plane in one region; data planes regional (gateway runs near data, control plane fans out policy bundles) |

## Reference topology (Kubernetes)

```
                     ┌──────────────────────────────┐
   ingress (NLB)  ──►│ praesidio-gateway (HPA 3-N)  │──► upstream LLMs
                     └──────────┬───────────────────┘
                                │
                  ┌─────────────┼───────────────────────┐
                  ▼             ▼                       ▼
            ┌─────────┐   ┌──────────┐         ┌─────────────────┐
            │ Postgres│   │ Redis    │         │ praesidio-ui    │
            │ primary │   │ (vault + │         │ (Next.js)       │
            │  + ro   │   │  cache)  │         └─────────────────┘
            └─────────┘   └──────────┘
```

NetworkPolicy: gateway egress restricted to listed upstream FQDNs + DB +
Redis. UI egress restricted to gateway admin API only.

## Helm values (excerpt)

```yaml
image:
  gateway: { repository: ghcr.io/praesidio/gateway, tag: "{{ .Chart.AppVersion }}" }
  ui:      { repository: ghcr.io/praesidio/ui,      tag: "{{ .Chart.AppVersion }}" }

replicas:
  gateway: 3
  ui: 2

resources:
  gateway:
    requests: { cpu: 500m, memory: 768Mi }
    limits:   { cpu: 2,    memory: 2Gi }

autoscaling:
  gateway: { minReplicas: 3, maxReplicas: 50, targetCPU: 65 }

policyBundle:
  source: configmap          # or 'http' or 's3' or 'git'
  signatureVerification: cosign
  publicKeyRef: praesidio-bundle-signing-pubkey

secrets:
  externalSecrets: true      # uses external-secrets-operator
  kmsRef: arn:aws:kms:...
```

## Secrets management

- All keys (vault, FPE, OIDC, upstream API keys) are referenced via
  `SecretKeyRef` / external-secrets-operator.
- KMS providers: AWS KMS, GCP KMS, Azure Key Vault, HashiCorp Vault.
- Optional Nitro Enclaves / Confidential Containers for keys at runtime.

## Observability

- **Logs**: structured JSON (zerologger-style) on stdout.
- **Metrics**: Prometheus `/metrics` — request count, decision distribution,
  per-detector latency histograms, vault hit/miss, upstream latency by
  provider.
- **Traces**: OpenTelemetry, exported via OTLP/gRPC. Trace context
  propagated to upstream LLM calls.

Dashboards in `deploy/grafana/`.

## Backups & disaster recovery

| Component | Strategy | RPO | RTO |
|---|---|---|---|
| Postgres (audit/lineage) | continuous WAL → S3 + nightly snapshots | 5 min | 1 hr |
| Redis (vault) | AOF + replica; data is ephemeral (TTL-bound) so loss is acceptable | n/a | 5 min |
| Policy bundles | Git (canonical) + S3 mirror | 0 | 1 min |

## Upgrades

- Gateway: zero-downtime rolling update. Sticky sessions not required.
- Postgres: blue/green; gateway tolerates a brief read failure with
  per-policy fail-mode.
- Policy bundle: hot reload, atomic swap, signature verified before swap.

## Terraform

`deploy/terraform/` contains a reference module for:
- AWS (EKS + RDS Postgres + ElastiCache Redis + KMS),
- Azure (AKS + Flexible Server + Cache for Redis + Key Vault),
- GCP (GKE + Cloud SQL + Memorystore + KMS).

Out of scope for the MVP repo: full network topology, identity-provider
integration. Stubs included.
