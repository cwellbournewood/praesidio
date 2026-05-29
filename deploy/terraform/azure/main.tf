################################################################################
# Praesidio reference Terraform — Azure
#
# !!! STUB QUALITY !!! Reference starting point, not turnkey production.
################################################################################

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  numeric = true
  special = false
}

locals {
  name = var.name_prefix
}

resource "azurerm_resource_group" "this" {
  name     = "${local.name}-rg"
  location = var.location
  tags     = var.tags
}

################################################################################
# Networking
################################################################################

resource "azurerm_virtual_network" "this" {
  name                = "${local.name}-vnet"
  address_space       = [var.vnet_cidr]
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = var.tags
}

resource "azurerm_subnet" "aks" {
  name                 = "aks"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 4, 0)]
}

resource "azurerm_subnet" "data" {
  name                 = "data"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 4, 1)]
  service_endpoints    = ["Microsoft.Storage", "Microsoft.KeyVault"]

  delegation {
    name = "flexible-postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

################################################################################
# Key Vault
################################################################################

resource "azurerm_key_vault" "this" {
  name                        = "${local.name}-${random_string.suffix.result}"
  location                    = azurerm_resource_group.this.location
  resource_group_name         = azurerm_resource_group.this.name
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "standard"
  purge_protection_enabled    = true
  soft_delete_retention_days  = 30
  enable_rbac_authorization   = true
  tags                        = var.tags
}

################################################################################
# Storage account (audit / lineage archival)
################################################################################

resource "azurerm_storage_account" "audit" {
  name                          = "praeaudit${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  account_tier                  = "Standard"
  account_replication_type      = var.storage_account_replication
  min_tls_version               = "TLS1_2"
  shared_access_key_enabled     = false
  public_network_access_enabled = false
  tags                          = var.tags

  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 30 }
  }
}

resource "azurerm_storage_container" "audit" {
  name                  = "audit"
  storage_account_name  = azurerm_storage_account.audit.name
  container_access_type = "private"
}

################################################################################
# Postgres Flexible Server
################################################################################

resource "azurerm_private_dns_zone" "postgres" {
  name                = "${local.name}.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.this.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "postgres-link"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.this.id
}

resource "random_password" "postgres" {
  length  = 32
  special = true
}

resource "azurerm_postgresql_flexible_server" "this" {
  name                          = "${local.name}-pg-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  version                       = "16"
  delegated_subnet_id           = azurerm_subnet.data.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  administrator_login           = var.postgres_admin_user
  administrator_password        = random_password.postgres.result
  zone                          = "1"
  storage_mb                    = var.postgres_storage_mb
  sku_name                      = var.postgres_sku
  backup_retention_days         = 14
  geo_redundant_backup_enabled  = false # set true for prod
  public_network_access_enabled = false
  tags                          = var.tags

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

resource "azurerm_postgresql_flexible_server_database" "praesidio" {
  name      = "praesidio"
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

################################################################################
# Azure Cache for Redis
################################################################################

resource "azurerm_redis_cache" "this" {
  name                          = "${local.name}-redis-${random_string.suffix.result}"
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  capacity                      = var.redis_capacity
  family                        = "C"
  sku_name                      = var.redis_sku
  minimum_tls_version           = "1.2"
  public_network_access_enabled = false
  non_ssl_port_enabled          = false
  tags                          = var.tags

  redis_configuration {
    maxmemory_policy = "allkeys-lru"
  }
}

################################################################################
# AKS
################################################################################

resource "azurerm_user_assigned_identity" "aks" {
  name                = "${local.name}-aks"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
}

resource "azurerm_kubernetes_cluster" "this" {
  name                       = local.name
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  dns_prefix                 = local.name
  kubernetes_version         = var.kubernetes_version
  oidc_issuer_enabled        = true
  workload_identity_enabled  = true
  azure_policy_enabled       = true
  tags                       = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks.id]
  }

  default_node_pool {
    name                 = "system"
    vm_size              = var.node_vm_size
    node_count           = var.node_count
    auto_scaling_enabled = true
    min_count            = var.node_min
    max_count            = var.node_max
    vnet_subnet_id       = azurerm_subnet.aks.id
    only_critical_addons_enabled = false
    upgrade_settings { max_surge = "33%" }
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "cilium"
    load_balancer_sku   = "standard"
  }

  role_based_access_control_enabled = true
}

################################################################################
# Federated identity for the praesidio gateway ServiceAccount (Workload Identity)
################################################################################

resource "azurerm_user_assigned_identity" "gateway" {
  name                = "${local.name}-gateway"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
}

resource "azurerm_federated_identity_credential" "gateway" {
  name                = "${local.name}-gateway-federation"
  resource_group_name = azurerm_resource_group.this.name
  parent_id           = azurerm_user_assigned_identity.gateway.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.this.oidc_issuer_url
  subject             = "system:serviceaccount:praesidio:praesidio"
}

resource "azurerm_role_assignment" "gateway_kv_secrets" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.gateway.principal_id
}

resource "azurerm_role_assignment" "gateway_kv_crypto" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Crypto User"
  principal_id         = azurerm_user_assigned_identity.gateway.principal_id
}

resource "azurerm_role_assignment" "gateway_storage" {
  scope                = azurerm_storage_account.audit.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.gateway.principal_id
}
