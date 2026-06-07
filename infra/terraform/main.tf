locals {
  labels = merge({
    project     = "food-crawl"
    environment = var.environment
    managed_by  = "terraform"
  }, var.labels)

  name_prefix   = "${var.name_prefix}-${var.environment}"
  bucket_prefix = coalesce(var.bucket_prefix, "${var.project_id}-${var.name_prefix}")

  # Medallion zones, top-of-funnel (raw) to bottom (train).
  zones = ["raw", "bronze", "silver", "gold", "train"]

  bucket_names = { for z in local.zones : z => "${local.bucket_prefix}-${z}" }
}
