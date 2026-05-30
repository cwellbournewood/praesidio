# Section — AWS reference Terraform

**Stub quality.** This module is a reference *starting point* — not a
turnkey production deployment. Review every resource and tune for your
environment before applying.

What it creates:

- VPC (2 AZs by default) with public + private subnets and a single NAT gateway
- KMS CMK (rotation enabled) used for RDS, ElastiCache, S3, and EKS-secret encryption
- S3 bucket for audit / lineage archival (versioned, KMS-encrypted, no public access)
- RDS Postgres 16 (single-AZ for demo; flip `postgres_multi_az = true` for prod)
- ElastiCache Redis (replication group, 2 nodes, encryption in transit and at rest)
- EKS cluster with a small managed node group
- OIDC provider + IRSA role + policy for the gateway ServiceAccount

## Apply

```bash
cd deploy/terraform/aws
terraform init
terraform plan -var region=us-east-1 -var name_prefix=section
terraform apply
```

## Teardown

**Warning:** the RDS instance has `deletion_protection = true` and the S3
bucket has versioning enabled. You must disable both manually before
`terraform destroy` can succeed:

```bash
aws rds modify-db-instance --db-instance-identifier section-postgres --no-deletion-protection --apply-immediately
aws s3api delete-objects --bucket <audit-bucket> --delete "$(aws s3api list-object-versions --bucket <audit-bucket> --output json --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}')"
terraform destroy
```

## Not included (intentionally)

- Identity provider integration (SSO, Cognito, etc.)
- Cluster autoscaler / Karpenter
- Private API endpoint only (current default exposes EKS public API)
- ALB ingress controller and external-dns
- Pinned, audited AMI for the node group
- Network firewall, GuardDuty findings routing, AWS Config rules
- Multi-region replication

## After apply

1. Authenticate kubectl:
   ```bash
   aws eks update-kubeconfig --name "$(terraform output -raw eks_cluster_name)" --region us-east-1
   ```
2. Annotate the gateway ServiceAccount via Helm values:
   ```yaml
   serviceAccount:
     annotations:
       eks.amazonaws.com/role-arn: "<terraform output gateway_irsa_role_arn>"
   ```
3. Install the chart with `postgres.embedded=false` / `redis.embedded=false`
   and set `postgres.externalDSN` + `redis.externalURL` to the RDS/ElastiCache
   endpoints emitted as outputs.
