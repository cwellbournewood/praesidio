# Secrets — Bitnami Sealed Secrets

Operationally simpler than ESO + a cloud KMS — sealed secrets are checked
into Git directly and decrypted in-cluster by the controller. Good for
small / air-gapped deployments where a managed secret store is not
available.

> Sealed Secrets is **not** equivalent to ExternalSecrets. The cluster
> public key is the only thing you need to seal, and the controller
> private key never leaves the cluster. Back the controller key up
> off-cluster — losing it makes every sealed secret unrecoverable.

## Step 1 — install the controller

```bash
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm upgrade --install sealed-secrets sealed-secrets/sealed-secrets \
    -n kube-system \
    --set fullnameOverride=sealed-secrets-controller \
    --version 2.16.1
```

Fetch and back up the public cert (for sealing) and the private key (for
disaster recovery):

```bash
kubeseal --fetch-cert > pub-sealed-secrets.pem
kubectl -n kube-system get secret \
    -l sealedsecrets.bitnami.com/sealed-secrets-key \
    -o yaml > sealed-secrets-master.yaml.SENSITIVE
# Move sealed-secrets-master.yaml.SENSITIVE to your offline backup (HSM,
# encrypted USB, KMS-wrapped object storage). Never commit it.
```

## Step 2 — seal the Praesidio gateway Secret

Compose the source Secret locally (do not commit this file):

```yaml
# praesidio-gateway-raw.yaml — do NOT commit
apiVersion: v1
kind: Secret
metadata:
  name: praesidio-gateway
  namespace: praesidio
type: Opaque
stringData:
  PRAESIDIO_VAULT_KEY: "<base64 of 32 bytes>"
  PRAESIDIO_FPE_KEY: "<hex 16 bytes>"
  PRAESIDIO_FPE_TWEAK: "<hex 7 bytes>"
  PRAESIDIO_API_KEYS: "<comma-separated bearer keys>"
  DATABASE_URL: "postgresql+asyncpg://praesidio:...@pg/praesidio?sslmode=verify-full"
  REDIS_URL: "rediss://praesidio:...@redis:6379/0"
  OPENAI_API_KEY: "sk-..."
  ANTHROPIC_API_KEY: "sk-ant-..."
```

Seal it and commit the output:

```bash
kubeseal --cert pub-sealed-secrets.pem \
    --format yaml \
    < praesidio-gateway-raw.yaml \
    > deploy/k8s/secrets/praesidio-gateway.sealed.yaml

shred -u praesidio-gateway-raw.yaml
git add deploy/k8s/secrets/praesidio-gateway.sealed.yaml
git commit -m "secrets: rotate praesidio-gateway sealed secret"
```

## Step 3 — disable the chart-emitted ExternalSecret

In your site values file:

```yaml
secrets:
  externalSecrets: false
  # values.* are left empty — the sealed-secret above provides everything.
```

## Step 4 — install / upgrade

```bash
kubectl apply -f deploy/k8s/secrets/praesidio-gateway.sealed.yaml
# Wait for the SealedSecret to materialise the underlying Secret:
kubectl -n praesidio get secret praesidio-gateway

helm upgrade --install praesidio deploy/helm/praesidio \
    -n praesidio --create-namespace \
    -f deploy/helm/praesidio/values.production.yaml \
    -f my-site-values.yaml
```

The chart will detect the externally-managed `Secret` and skip emitting
its own — it always uses `envFrom: secretRef` so any Secret with the
expected name and keys works.

## Rotation

Re-run Step 2 with the new values, commit, and `kubectl apply -f`. Then
`kubectl rollout restart deploy/praesidio-gateway`.

## Disaster recovery

If you lose the controller's master key, every previously-sealed secret
is permanently unreadable. Restore from your off-cluster backup:

```bash
kubectl apply -f /path/to/backup/sealed-secrets-master.yaml.SENSITIVE
kubectl -n kube-system rollout restart deploy/sealed-secrets-controller
```
