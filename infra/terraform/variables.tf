variable "project_id" {
  description = "GCP project ID that hosts the food-crawl platform."
  type        = string
}

variable "region" {
  description = "Primary GCP region for regional resources (buckets, subnet, Cloud SQL)."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Default zone within the region."
  type        = string
  default     = "us-central1-a"
}

variable "environment" {
  description = "Deployment environment short name (e.g. dev, staging, prod). Used in resource names and labels."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,15}$", var.environment))
    error_message = "environment must be lowercase alphanumeric/hyphen, starting with a letter, <= 16 chars."
  }
}

variable "name_prefix" {
  description = "Prefix applied to named resources (network, Cloud SQL, service accounts, etc.)."
  type        = string
  default     = "chi-food"
}

variable "bucket_prefix" {
  description = "Globally-unique prefix for GCS bucket names. Defaults to \"<project_id>-chi-food\" to avoid collisions. Set explicitly (e.g. \"chi-food\") only if you own those names."
  type        = string
  default     = null
}

variable "bucket_location" {
  description = "Location for GCS buckets (region or multi-region such as US)."
  type        = string
  default     = "US"
}

variable "labels" {
  description = "Additional labels merged onto every resource."
  type        = map(string)
  default     = {}
}

# --- Networking ---

variable "subnet_cidr" {
  description = "Primary CIDR for the workload subnet."
  type        = string
  default     = "10.10.0.0/20"
}

variable "pods_cidr" {
  description = "Secondary CIDR range for GKE pods."
  type        = string
  default     = "10.20.0.0/16"
}

variable "services_cidr" {
  description = "Secondary CIDR range for GKE services."
  type        = string
  default     = "10.30.0.0/20"
}

# --- Cloud SQL ---

variable "db_tier" {
  description = "Cloud SQL machine tier for the URL frontier database."
  type        = string
  default     = "db-custom-1-3840"
}

variable "db_version" {
  description = "Cloud SQL Postgres version."
  type        = string
  default     = "POSTGRES_15"
}

variable "db_name" {
  description = "Name of the frontier database."
  type        = string
  default     = "frontier"
}

variable "db_user" {
  description = "Application database user for crawler/processing workloads."
  type        = string
  default     = "crawler"
}

variable "db_disk_size_gb" {
  description = "Initial Cloud SQL data disk size in GB (autoresize is enabled)."
  type        = number
  default     = 20
}

variable "db_availability_type" {
  description = "Cloud SQL availability: ZONAL (cheaper) or REGIONAL (HA)."
  type        = string
  default     = "ZONAL"
}

variable "db_deletion_protection" {
  description = "Protect the Cloud SQL instance from accidental deletion."
  type        = bool
  default     = true
}

# --- Application config ---

variable "crawler_contact_email" {
  description = "Contact email advertised in the crawler User-Agent and stored in Secret Manager."
  type        = string
  default     = "contact@example.com"
}
