variable "location" {
  description = "Azure region."
  type        = string
  default     = "westeurope"
}

variable "name_prefix" {
  description = "Prefix for all resources."
  type        = string
  default     = "section"
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default = {
    project    = "section"
    managed_by = "terraform"
  }
}

variable "vnet_cidr" {
  description = "Virtual network CIDR."
  type        = string
  default     = "10.50.0.0/16"
}

variable "kubernetes_version" {
  description = "AKS Kubernetes version."
  type        = string
  default     = "1.30"
}

variable "node_vm_size" {
  description = "AKS node VM size."
  type        = string
  default     = "Standard_D4s_v5"
}

variable "node_count" {
  description = "Initial AKS node count."
  type        = number
  default     = 2
}

variable "node_min" {
  description = "AKS node pool minimum."
  type        = number
  default     = 2
}

variable "node_max" {
  description = "AKS node pool maximum."
  type        = number
  default     = 6
}

variable "postgres_sku" {
  description = "Postgres Flexible Server SKU."
  type        = string
  default     = "GP_Standard_D2s_v3"
}

variable "postgres_storage_mb" {
  description = "Postgres storage in MB."
  type        = number
  default     = 65536
}

variable "postgres_admin_user" {
  description = "Postgres admin user."
  type        = string
  default     = "section"
}

variable "redis_sku" {
  description = "Azure Cache for Redis SKU name (Basic / Standard / Premium)."
  type        = string
  default     = "Standard"
}

variable "redis_capacity" {
  description = "Redis capacity (0..6 depending on SKU)."
  type        = number
  default     = 1
}

variable "storage_account_replication" {
  description = "Storage replication type. LRS for demo, GZRS for prod."
  type        = string
  default     = "LRS"
}
