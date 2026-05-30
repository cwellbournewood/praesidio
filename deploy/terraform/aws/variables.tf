variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix applied to all named resources."
  type        = string
  default     = "section"
}

variable "tags" {
  description = "Common tags applied to every resource."
  type        = map(string)
  default = {
    Project   = "section"
    ManagedBy = "terraform"
  }
}

variable "vpc_cidr" {
  description = "CIDR for the VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "azs" {
  description = "Availability zones to deploy into. Pick two for demo, three for prod."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version."
  type        = string
  default     = "1.30"
}

variable "node_instance_type" {
  description = "EC2 instance type for the EKS node group."
  type        = string
  default     = "m6i.large"
}

variable "node_desired_size" {
  description = "Desired number of EKS nodes."
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum EKS nodes."
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Maximum EKS nodes."
  type        = number
  default     = 6
}

variable "postgres_version" {
  description = "RDS Postgres engine version."
  type        = string
  default     = "16.3"
}

variable "postgres_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "postgres_allocated_storage" {
  description = "Allocated storage in GiB."
  type        = number
  default     = 50
}

variable "postgres_multi_az" {
  description = "Multi-AZ deployment. true for prod."
  type        = bool
  default     = false
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.small"
}

variable "audit_bucket_name" {
  description = "Optional override for the audit S3 bucket name. If empty, a random suffix is appended."
  type        = string
  default     = ""
}

variable "irsa_namespace" {
  description = "Kubernetes namespace the gateway runs in (used for IRSA trust policy)."
  type        = string
  default     = "section"
}

variable "irsa_service_account" {
  description = "Kubernetes ServiceAccount name (used for IRSA trust policy)."
  type        = string
  default     = "section"
}
