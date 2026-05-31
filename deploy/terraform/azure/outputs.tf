output "resource_group" {
  value = azurerm_resource_group.this.name
}

output "aks_name" {
  value = azurerm_kubernetes_cluster.this.name
}

output "aks_oidc_issuer" {
  value = azurerm_kubernetes_cluster.this.oidc_issuer_url
}

output "key_vault_uri" {
  value = azurerm_key_vault.this.vault_uri
}

output "audit_storage_account" {
  value = azurerm_storage_account.audit.name
}

output "postgres_fqdn" {
  value     = azurerm_postgresql_flexible_server.this.fqdn
  sensitive = true
}

output "postgres_admin_password" {
  value     = random_password.postgres.result
  sensitive = true
}

output "redis_hostname" {
  value     = azurerm_redis_cache.this.hostname
  sensitive = true
}

output "redis_primary_access_key" {
  value     = azurerm_redis_cache.this.primary_access_key
  sensitive = true
}

output "gateway_workload_identity_client_id" {
  description = "Set on the gateway ServiceAccount via azure.workload.identity/client-id annotation."
  value       = azurerm_user_assigned_identity.gateway.client_id
}
