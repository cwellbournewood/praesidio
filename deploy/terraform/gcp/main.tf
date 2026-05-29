################################################################################
# Praesidio reference Terraform — GCP
#
# !!! STUB QUALITY !!! Reference starting point, not turnkey production.
################################################################################

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  name        = var.name_prefix
  bucket_name = "${var.project_id}-${var.name_prefix}-audit-${random_id.suffix.hex}"
}

################################################################################
# Required services
################################################################################

resource "google_project_service" "services" {
  for_each = toset([
    "container.googleapis.com",
    "compute.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "cloudkms.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "servicenetworking.googleapis.com",
    "secretmanager.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

################################################################################
# VPC
################################################################################

resource "google_compute_network" "this" {
  name                    = "${local.name}-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.services]
}

resource "google_compute_subnetwork" "this" {
  name          = "${local.name}-subnet"
  region        = var.region
  network       = google_compute_network.this.id
  ip_cidr_range = var.vpc_cidr

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }

  private_ip_google_access = true
}

# Cloud Router + NAT for egress from private GKE Autopilot
resource "google_compute_router" "this" {
  name    = "${local.name}-router"
  region  = var.region
  network = google_compute_network.this.id
}

resource "google_compute_router_nat" "this" {
  name                               = "${local.name}-nat"
  router                             = google_compute_router.this.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# Private services access for Cloud SQL
resource "google_compute_global_address" "psa" {
  name          = "${local.name}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.this.id
}

resource "google_service_networking_connection" "psa" {
  network                 = google_compute_network.this.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.psa.name]
}

################################################################################
# KMS
################################################################################

resource "google_kms_key_ring" "this" {
  name       = "${local.name}-keyring"
  location   = var.region
  depends_on = [google_project_service.services]
}

resource "google_kms_crypto_key" "data" {
  name            = "${local.name}-data"
  key_ring        = google_kms_key_ring.this.id
  rotation_period = "7776000s" # 90 days
  purpose         = "ENCRYPT_DECRYPT"
  lifecycle { prevent_destroy = true }
}

################################################################################
# GCS — audit / lineage archival
################################################################################

resource "google_storage_bucket" "audit" {
  name                        = local.bucket_name
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = var.labels

  versioning { enabled = true }

  lifecycle_rule {
    condition { age = 365 }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}

################################################################################
# Cloud SQL Postgres (private IP)
################################################################################

resource "random_password" "postgres" {
  length  = 32
  special = true
}

resource "google_sql_database_instance" "postgres" {
  name             = "${local.name}-pg-${random_id.suffix.hex}"
  database_version = "POSTGRES_16"
  region           = var.region

  depends_on = [google_service_networking_connection.psa]

  settings {
    tier              = var.postgres_tier
    availability_type = "REGIONAL"      # ZONAL for demo / cost-saving
    disk_size         = 50
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.this.id
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = false
      record_client_address   = false
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "praesidio" {
  name     = "praesidio"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "praesidio" {
  name     = "praesidio"
  instance = google_sql_database_instance.postgres.name
  password = random_password.postgres.result
}

################################################################################
# Memorystore Redis
################################################################################

resource "google_redis_instance" "this" {
  name                    = "${local.name}-redis"
  tier                    = var.redis_tier
  memory_size_gb          = var.redis_size_gb
  region                  = var.region
  authorized_network      = google_compute_network.this.id
  redis_version           = "REDIS_7_2"
  connect_mode            = "PRIVATE_SERVICE_ACCESS"
  transit_encryption_mode = "SERVER_AUTHENTICATION"
  auth_enabled            = true
  depends_on              = [google_service_networking_connection.psa]
}

################################################################################
# GKE Autopilot
################################################################################

resource "google_container_cluster" "this" {
  provider = google-beta

  name             = local.name
  location         = var.region
  enable_autopilot = true
  network          = google_compute_network.this.id
  subnetwork       = google_compute_subnetwork.this.id

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  release_channel { channel = "REGULAR" }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  deletion_protection = true

  depends_on = [google_project_service.services]
}

################################################################################
# Service account for the gateway, bound via Workload Identity
################################################################################

resource "google_service_account" "gateway" {
  account_id   = "${local.name}-gateway"
  display_name = "Praesidio gateway"
}

resource "google_kms_crypto_key_iam_member" "gateway_kms" {
  crypto_key_id = google_kms_crypto_key.data.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.gateway.email}"
}

resource "google_storage_bucket_iam_member" "gateway_audit" {
  bucket = google_storage_bucket.audit.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.gateway.email}"
}

resource "google_project_iam_member" "gateway_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.gateway.email}"
}

# Workload Identity binding to the Kubernetes ServiceAccount
resource "google_service_account_iam_member" "gateway_wi" {
  service_account_id = google_service_account.gateway.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.gateway_ksa_namespace}/${var.gateway_ksa_name}]"
}
