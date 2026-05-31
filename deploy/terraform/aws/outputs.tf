output "eks_cluster_name" {
  value = aws_eks_cluster.this.name
}

output "eks_cluster_endpoint" {
  value     = aws_eks_cluster.this.endpoint
  sensitive = true
}

output "eks_oidc_issuer" {
  value = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

output "kms_key_arn" {
  value = aws_kms_key.section.arn
}

output "audit_bucket_name" {
  value = aws_s3_bucket.audit.bucket
}

output "postgres_endpoint" {
  value     = aws_db_instance.postgres.endpoint
  sensitive = true
}

output "redis_primary_endpoint" {
  value     = aws_elasticache_replication_group.redis.primary_endpoint_address
  sensitive = true
}

output "gateway_irsa_role_arn" {
  description = "Annotate the gateway ServiceAccount with this ARN via serviceAccount.annotations[eks.amazonaws.com/role-arn]."
  value       = aws_iam_role.gateway.arn
}

output "vpc_id" {
  value = aws_vpc.this.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}
