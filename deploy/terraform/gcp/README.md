# Praesidio — GCP reference Terraform

**Stub quality.** Reference *starting point*, not a turnkey production
deployment.

What it creates:

- VPC + subnet (with secondary ranges for pods/services), Cloud NAT, private
  services access for Cloud SQL
- KMS key ring + rotating CMK
- GCS bucket for audit / lineage archival (versioned, uniform bucket-level
  access, public-access-prevention enforced)
- Cloud SQL Postgres 16 (private IP, regional HA, PITR)
- Memorystore Redis (Standard HA, TLS, AUTH)
- GKE Autopilot (Workload Identity enabled)
- Google service account for the gateway + Workload Identity binding to the
  `praesidio/praesidio` Kubernetes ServiceAccount

## Apply

```bash
cd deploy/terraform/gcp
gcloud auth application-default login
terraform init
terraform plan -var project_id=my-project -var region=europe-west1
terraform apply
```

## Teardown

The Cloud SQL instance and GKE cluster both have `deletion_protection = true`,
and the KMS crypto key has `prevent_destroy = true`. Disable each manually
(or `terraform state rm` the KMS key and let it sit unused — KMS keys
cannot be deleted, only destroyed-with-restore-window).

## After apply

```bash
gcloud container clusters get-credentials "$(terraform output -raw gke_name)" --region "<region>"
```

Helm values:

```yaml
serviceAccount:
  annotations:
    iam.gke.io/gcp-service-account: "<terraform output gateway_service_account_email>"
postgres:
  embedded: false
  externalDSN: "postgresql+asyncpg://praesidio:<password>@<private_ip>:5432/praesidio"
redis:
  embedded: false
  externalURL: "rediss://:<auth_string>@<redis_host>:6379/0"
```

## Not included

- Private GKE control-plane only access (Autopilot regional default is mixed)
- VPC Service Controls perimeter
- Cloud Armor + GCLB ingress
- Cloud Logging sinks for audit shipping
- Multi-region failover
