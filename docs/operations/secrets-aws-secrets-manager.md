# Secrets — AWS Secrets Manager (via External Secrets Operator)

End-to-end walkthrough for delivering Praesidio's runtime secrets from AWS
Secrets Manager into the Kubernetes namespace where the gateway runs, using
the [External Secrets Operator (ESO)](https://external-secrets.io).

## What the gateway needs

| Secret key in Secrets Manager | Env var injected | Purpose |
|---|---|---|
| `praesidio/gateway/vault-key` | `PRAESIDIO_VAULT_KEY` | AES-256 master key for the reversible-tokenisation vault. Base64-encoded 32 bytes. |
| `praesidio/gateway/fpe-key` | `PRAESIDIO_FPE_KEY` | FF3-1 key (16 hex bytes / AES-128). |
| `praesidio/gateway/fpe-tweak` | `PRAESIDIO_FPE_TWEAK` | FF3-1 tweak (7 hex bytes). |
| `praesidio/gateway/api-keys` | `PRAESIDIO_API_KEYS` | Comma-separated bearer keys allowed at the gateway edge. |
| `praesidio/gateway/database-url` | `DATABASE_URL` | Postgres DSN, including `?sslmode=verify-full`. |
| `praesidio/gateway/redis-url` | `REDIS_URL` | Redis URL, TLS-enabled. |
| `praesidio/upstream/openai` | `OPENAI_API_KEY` | Optional upstream key. |
| `praesidio/upstream/anthropic` | `ANTHROPIC_API_KEY` | Optional upstream key. |
| `praesidio/upstream/azure-openai` | `AZURE_OPENAI_API_KEY` | Optional upstream key. |

All entries are stored as **SecretString** JSON with a single `value` field —
this is the simplest layout ESO understands. Adapt as your platform conventions
require (e.g. one Secrets Manager secret per environment, with multiple JSON
keys), but keep the IRSA role's `kms:Decrypt` and `secretsmanager:GetSecretValue`
scope as narrow as possible.

## Step 1 — install ESO

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm upgrade --install external-secrets external-secrets/external-secrets \
    -n external-secrets --create-namespace \
    --version 0.10.4 \
    --set installCRDs=true \
    --set webhook.port=9443
```

Verify:

```bash
kubectl -n external-secrets get pods
kubectl get crd | grep external-secrets.io
```

## Step 2 — IRSA (or Workload Identity / Pod Identity) for ESO

ESO needs an IAM identity that can read the Praesidio secrets. The simplest
clean pattern is IRSA on the ESO ServiceAccount.

1. Create the IAM policy (least-privilege, prefix-scoped):

   ```bash
   cat > praesidio-secrets-read.json <<'JSON'
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "ReadPraesidioSecrets",
         "Effect": "Allow",
         "Action": [
           "secretsmanager:GetSecretValue",
           "secretsmanager:DescribeSecret"
         ],
         "Resource": [
           "arn:aws:secretsmanager:us-east-1:111122223333:secret:praesidio/*"
         ]
       },
       {
         "Sid": "DecryptKMS",
         "Effect": "Allow",
         "Action": ["kms:Decrypt"],
         "Resource": ["arn:aws:kms:us-east-1:111122223333:key/<kms-key-id>"]
       }
     ]
   }
   JSON

   aws iam create-policy --policy-name PraesidioSecretsRead \
       --policy-document file://praesidio-secrets-read.json
   ```

2. Create the IRSA role and bind to the ESO ServiceAccount
   (`external-secrets/external-secrets`):

   ```bash
   eksctl create iamserviceaccount \
       --cluster <your-cluster> \
       --namespace external-secrets \
       --name external-secrets \
       --attach-policy-arn arn:aws:iam::111122223333:policy/PraesidioSecretsRead \
       --override-existing-serviceaccounts \
       --approve
   ```

3. Restart the ESO controller to pick up the annotation:

   ```bash
   kubectl -n external-secrets rollout restart deploy/external-secrets
   ```

## Step 3 — ClusterSecretStore

```yaml
# clustersecretstore-praesidio.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: praesidio
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      # No `auth:` block — falls back to the ESO controller's IRSA identity.
```

```bash
kubectl apply -f clustersecretstore-praesidio.yaml
kubectl get clustersecretstore praesidio -o yaml | grep -A2 conditions:
# Expect: Ready=True
```

## Step 4 — Materialise the gateway Secret

The Helm chart already ships `templates/externalsecret-gateway.yaml`. With
`secrets.externalSecrets=true` (the default in `values.production.yaml`), it
emits a `Kind: ExternalSecret` that pulls each entry under
`secrets.remoteKeys.*` and writes a single in-cluster `Secret` named
`<release>-gateway`. Confirm after the upgrade:

```bash
kubectl -n praesidio get externalsecret praesidio-gateway -o yaml | grep -A3 status:
kubectl -n praesidio get secret praesidio-gateway -o yaml | grep -E "^(  )?[A-Z_]+:" | head -20
```

## Step 5 — `helm upgrade --install`

```bash
helm upgrade --install praesidio deploy/helm/praesidio \
    -n praesidio --create-namespace \
    -f deploy/helm/praesidio/values.production.yaml \
    -f my-site-values.yaml

# my-site-values.yaml typically only overrides:
#   image.gateway.tag, image.ui.tag, ingress.*, secrets.kmsRef
```

`helm upgrade` will:

1. Apply the `ExternalSecret` and wait for ESO to write the underlying Secret.
2. Run the pre-upgrade migration `Job` (uses Alembic).
3. Roll out the gateway / UI Deployments with the env vars referenced from
   the materialised Secret.

## Step 6 — Verification

```bash
# All pods Ready
kubectl -n praesidio get pods

# Gateway healthy
kubectl -n praesidio port-forward svc/praesidio-gateway 8080:8080 &
curl -sf http://localhost:8080/healthz && echo OK

# Secret was actually populated by ESO (not just an empty stub)
kubectl -n praesidio get secret praesidio-gateway \
    -o jsonpath='{.data.PRAESIDIO_VAULT_KEY}' | base64 -d | wc -c
# Expect: 44 (base64 of 32 bytes)

# Run a tokenisation request through the gateway
curl -sf http://localhost:8080/v1/chat/completions \
    -H "Authorization: Bearer $(kubectl -n praesidio get secret praesidio-gateway \
            -o jsonpath='{.data.PRAESIDIO_API_KEYS}' | base64 -d | cut -d, -f1)" \
    -H 'content-type: application/json' \
    -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"mail a@b.com"}]}'
```

## Rotation

Update the secret value in AWS Secrets Manager. ESO re-fetches every
`spec.refreshInterval` (default 1h on the chart's ExternalSecret). To force
an immediate refresh:

```bash
kubectl -n praesidio annotate externalsecret praesidio-gateway \
    force-sync="$(date +%s)" --overwrite
```

Then trigger a rolling restart so the gateway pods pick up the new env values:

```bash
kubectl -n praesidio rollout restart deploy/praesidio-gateway
```

> **Vault-key rotation is special.** Rotating `PRAESIDIO_VAULT_KEY` makes the
> existing token vault entries unrecoverable. Use the documented two-key
> rotation procedure in `docs/operations/disaster-recovery.md` before
> changing this value in production.
