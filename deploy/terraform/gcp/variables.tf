variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "europe-west1"
}

variable "name_prefix" {
  description = "Prefix for all resources."
  type        = string
  default     = "section"
}

variable "labels" {
  description = "Labels applied to all resources."
  type        = map(string)
  default = {
    project    = "section"
    managed_by = "terraform"
  }
}

variable "vpc_cidr" {
  description = "Primary subnet CIDR."
  type        = string
  default     = "10.60.0.0/20"
}

variable "pods_cidr" {
  description = "Secondary range for pods."
  type        = string
  default     = "10.61.0.0/16"
}

variable "services_cidr" {
  description = "Secondary range for services."
  type        = string
  default     = "10.62.0.0/20"
}

variable "postgres_tier" {
  description = "Cloud SQL tier."
  type        = string
  default     = "db-custom-2-7680"
}

variable "redis_size_gb" {
  description = "Memorystore Redis size in GB."
  type        = number
  default     = 1
}

variable "redis_tier" {
  description = "Memorystore tier (BASIC or STANDARD_HA)."
  type        = string
  default     = "STANDARD_HA"
}

variable "gateway_ksa_namespace" {
  description = "Kubernetes namespace for the gateway."
  type        = string
  default     = "section"
}

variable "gateway_ksa_name" {
  description = "Kubernetes ServiceAccount name (Workload Identity)."
  type        = string
  default     = "section"
}
