output "gke_name" {
  value = google_container_cluster.this.name
}

output "gke_endpoint" {
  value     = google_container_cluster.this.endpoint
  sensitive = true
}

output "kms_key_id" {
  value = google_kms_crypto_key.data.id
}

output "audit_bucket" {
  value = google_storage_bucket.audit.name
}

output "postgres_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "postgres_private_ip" {
  value     = google_sql_database_instance.postgres.private_ip_address
  sensitive = true
}

output "postgres_password" {
  value     = random_password.postgres.result
  sensitive = true
}

output "redis_host" {
  value     = google_redis_instance.this.host
  sensitive = true
}

output "redis_auth_string" {
  value     = google_redis_instance.this.auth_string
  sensitive = true
}

output "gateway_service_account_email" {
  description = "Annotate the gateway KSA with iam.gke.io/gcp-service-account = <this>."
  value       = google_service_account.gateway.email
}
