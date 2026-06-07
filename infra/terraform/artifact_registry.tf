# Container images for the crawler workers and Ray processing jobs.
resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = "${var.name_prefix}-containers"
  description   = "Container images for food-crawl crawler and Ray processing jobs."
  format        = "DOCKER"
  project       = var.project_id

  docker_config {
    immutable_tags = false
  }

  depends_on = [google_project_service.enabled]
}
