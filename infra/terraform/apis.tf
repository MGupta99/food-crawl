# Enable the GCP APIs the platform needs. Kept broad enough to cover later
# milestones (GKE, Ray on GKE, Cloud Composer) so they don't block follow-on work.
locals {
  required_apis = [
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
    "storage.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "container.googleapis.com",
    "composer.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each = toset(local.required_apis)

  project = var.project_id
  service = each.key

  disable_on_destroy         = false
  disable_dependent_services = false
}
