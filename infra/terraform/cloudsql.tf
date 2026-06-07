# URL frontier database (frontier_urls, host_state, crawl_runs). Private IP only,
# reached over the VPC peering established in network.tf.
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_database_instance" "frontier" {
  name             = "${local.name_prefix}-frontier"
  region           = var.region
  database_version = var.db_version
  project          = var.project_id

  deletion_protection = var.db_deletion_protection

  settings {
    tier              = var.db_tier
    availability_type = var.db_availability_type
    disk_size         = var.db_disk_size_gb
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
    }

    insights_config {
      query_insights_enabled = true
    }

    database_flags {
      name  = "max_connections"
      value = "200"
    }

    user_labels = local.labels
  }

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

resource "google_sql_database" "frontier" {
  name     = var.db_name
  instance = google_sql_database_instance.frontier.name
  project  = var.project_id
}

resource "google_sql_user" "app" {
  name     = var.db_user
  instance = google_sql_database_instance.frontier.name
  password = random_password.db.result
  project  = var.project_id
}
