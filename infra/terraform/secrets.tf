# --- Database password ---
resource "google_secret_manager_secret" "db_password" {
  secret_id = "${local.name_prefix}-db-password"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

# --- Full DB connection details (handy for app config) ---
resource "google_secret_manager_secret" "db_connection" {
  secret_id = "${local.name_prefix}-db-connection"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "db_connection" {
  secret = google_secret_manager_secret.db_connection.id
  secret_data = jsonencode({
    instance_connection_name = google_sql_database_instance.frontier.connection_name
    private_ip               = google_sql_database_instance.frontier.private_ip_address
    database                 = google_sql_database.frontier.name
    user                     = google_sql_user.app.name
    password                 = random_password.db.result
  })
}

# --- Crawler contact email (advertised in User-Agent) ---
resource "google_secret_manager_secret" "crawler_contact_email" {
  secret_id = "${local.name_prefix}-crawler-contact-email"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "crawler_contact_email" {
  secret      = google_secret_manager_secret.crawler_contact_email.id
  secret_data = var.crawler_contact_email
}
