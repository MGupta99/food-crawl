# Workload identities. Two least-privilege service accounts:
#   - crawler:    GKE fetcher workers (write raw, read/write frontier via Cloud SQL)
#   - processing: Ray jobs (read raw, write bronze/silver/gold/train)
resource "google_service_account" "crawler" {
  account_id   = "${local.name_prefix}-crawler"
  display_name = "Food-crawl focused crawler (GKE)"
  project      = var.project_id

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "processing" {
  account_id   = "${local.name_prefix}-processing"
  display_name = "Food-crawl Ray processing jobs"
  project      = var.project_id

  depends_on = [google_project_service.enabled]
}

locals {
  # Project-level roles shared by both workload SAs.
  common_project_roles = [
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/artifactregistry.reader",
    "roles/secretmanager.secretAccessor",
  ]

  crawler_project_roles = concat(local.common_project_roles, [
    "roles/cloudsql.client",
  ])

  processing_project_roles = local.common_project_roles

  # Flatten (sa, role) pairs so we can use a single for_each per SA.
  crawler_role_bindings    = { for r in local.crawler_project_roles : r => r }
  processing_role_bindings = { for r in local.processing_project_roles : r => r }
}

resource "google_project_iam_member" "crawler" {
  for_each = local.crawler_role_bindings

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.crawler.email}"
}

resource "google_project_iam_member" "processing" {
  for_each = local.processing_role_bindings

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.processing.email}"
}

# --- Bucket-level access (least privilege per zone) ---

# Crawler writes raw artifacts.
resource "google_storage_bucket_iam_member" "crawler_raw_admin" {
  bucket = google_storage_bucket.zones["raw"].name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.crawler.email}"
}

# Processing reads raw...
resource "google_storage_bucket_iam_member" "processing_raw_viewer" {
  bucket = google_storage_bucket.zones["raw"].name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.processing.email}"
}

# ...and read/writes every downstream zone.
resource "google_storage_bucket_iam_member" "processing_downstream_admin" {
  for_each = toset(["bronze", "silver", "gold", "train"])

  bucket = google_storage_bucket.zones[each.key].name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.processing.email}"
}
