# Praesidio — Azure reference Terraform

**Stub quality.** Reference *starting point*, not a turnkey production
deployment.

What it creates:

- Resource group, VNet, AKS + data subnets
- Key Vault (RBAC mode, purge protection on)
- Storage account + container for audit / lineage archival
- Postgres Flexible Server (private, in delegated subnet)
- Azure Cache for Redis (TLS-only)
- AKS cluster with OIDC issuer + Workload Identity enabled, Cilium network policy
- User-assigned managed identity + federated credential mapped to the
  `praesidio/praesidio` Kubernetes ServiceAccount, with Key Vault Secrets
  User, Key Vault Crypto User, and Storage Blob Data Contributor roles

## Apply

```bash
cd deploy/terraform/azure
az login
terraform init
terraform plan -var location=westeurope
terraform apply
```

## Teardown

The Key Vault has purge protection and 30-day soft-delete retention. Full
deletion requires either waiting out the retention or manual purge after
`terraform destroy`. Storage account has versioning + 30-day delete
retention — purge versions first if you need a clean tear-down.

## After apply

```bash
az aks get-credentials --resource-group "$(terraform output -raw resource_group)" --name "$(terraform output -raw aks_name)"
```

Helm values to set:

```yaml
serviceAccount:
  annotations:
    azure.workload.identity/client-id: "<terraform output gateway_workload_identity_client_id>"
postgres:
  embedded: false
  externalDSN: "postgresql+asyncpg://praesidio:<password>@<fqdn>:5432/praesidio?ssl=require"
redis:
  embedded: false
  externalURL: "rediss://:<key>@<hostname>:6380/0"
```

## Not included

- Private cluster (API server public by default — restrict for prod)
- Application Gateway / Front Door ingress
- Log Analytics workspace + Container Insights wiring
- Multi-region pairing
- Customer-managed keys for storage / Postgres (uses platform-managed)
