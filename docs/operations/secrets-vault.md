# Secrets — HashiCorp Vault (via External Secrets Operator)

Same workflow as
[`secrets-aws-secrets-manager.md`](secrets-aws-secrets-manager.md), but
backed by HashiCorp Vault's KV v2 engine.

## Prerequisites

* A Vault server reachable from the cluster (in-cluster Helm release or
  external).
* Vault is initialised, unsealed, and a KV v2 mount exists at `kv/`.
* The Kubernetes auth method is enabled on Vault.

## Step 1 — Vault policy + role

```hcl
# policy: praesidio-read.hcl
path "kv/data/praesidio/*" {
  capabilities = ["read"]
}
path "kv/metadata/praesidio/*" {
  capabilities = ["read"]
}
```

```bash
vault policy write praesidio-read praesidio-read.hcl
vault write auth/kubernetes/role/praesidio \
    bound_service_account_names=external-secrets \
    bound_service_account_namespaces=external-secrets \
    policies=praesidio-read \
    ttl=1h
```

## Step 2 — Seed the secrets

```bash
vault kv put kv/praesidio/gateway/vault-key   value="$(openssl rand -base64 32)"
vault kv put kv/praesidio/gateway/fpe-key     value="$(openssl rand -hex 16)"
vault kv put kv/praesidio/gateway/fpe-tweak   value="$(openssl rand -hex 7)"
vault kv put kv/praesidio/gateway/api-keys    value="$(openssl rand -hex 32)"
vault kv put kv/praesidio/gateway/database-url value="postgresql+asyncpg://praesidio:...@pg/praesidio?sslmode=verify-full"
vault kv put kv/praesidio/gateway/redis-url   value="rediss://praesidio:...@redis:6379/0"
vault kv put kv/praesidio/upstream/openai     value="sk-..."
vault kv put kv/praesidio/upstream/anthropic  value="sk-ant-..."
```

## Step 3 — ClusterSecretStore

```yaml
# clustersecretstore-praesidio-vault.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: praesidio
spec:
  provider:
    vault:
      server: "https://vault.vault.svc.cluster.local:8200"
      path: "kv"
      version: "v2"
      caProvider:
        type: ConfigMap
        name: vault-ca
        namespace: external-secrets
        key: ca.crt
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "praesidio"
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

```bash
kubectl apply -f clustersecretstore-praesidio-vault.yaml
kubectl get clustersecretstore praesidio -o yaml | grep -A2 conditions:
```

## Step 4 — install the chart

The chart's `templates/externalsecret-gateway.yaml` is provider-agnostic;
the `remoteRef.key` values map to Vault KV v2 paths (the `data/` prefix is
added by ESO internally). No other chart change needed.

```bash
helm upgrade --install praesidio deploy/helm/praesidio \
    -n praesidio --create-namespace \
    -f deploy/helm/praesidio/values.production.yaml \
    -f my-site-values.yaml
```

## Step 5 — verification

Same commands as in the AWS doc, plus:

```bash
# Confirm Vault leases on the ESO side
kubectl -n praesidio describe externalsecret praesidio-gateway | grep -i status
```

## Rotation

`vault kv put kv/praesidio/gateway/<key> value=<new>` then bump the
ExternalSecret `force-sync` annotation and rollout-restart the gateway.

> ESO does not by itself revoke old Vault leases. If you require strict
> key revocation semantics, pair the rotation with a `vault token revoke`
> against the role's tokens after the new value has propagated.
