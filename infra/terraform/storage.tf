# Medallion buckets: raw -> bronze -> silver -> gold -> train.
# Raw is the immutable landing zone (object versioning on, no auto-delete).
resource "google_storage_bucket" "zones" {
  for_each = local.bucket_names

  name     = each.value
  location = var.bucket_location
  project  = var.project_id

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  # Keep noncurrent (overwritten/old) versions bounded so storage doesn't grow
  # unbounded, while preserving the latest object indefinitely.
  lifecycle_rule {
    condition {
      num_newer_versions = 3
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    zone = each.key
  }

  depends_on = [google_project_service.enabled]
}
