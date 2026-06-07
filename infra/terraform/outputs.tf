output "project_id" {
  description = "GCP project hosting the platform."
  value       = var.project_id
}

output "region" {
  description = "Primary region."
  value       = var.region
}

output "bucket_names" {
  description = "Map of medallion zone -> GCS bucket name."
  value       = { for z, b in google_storage_bucket.zones : z => b.name }
}

output "bucket_urls" {
  description = "Map of medallion zone -> gs:// URL."
  value       = { for z, b in google_storage_bucket.zones : z => "gs://${b.name}" }
}

output "network" {
  description = "VPC network self link."
  value       = google_compute_network.vpc.self_link
}

output "subnetwork" {
  description = "Workload subnetwork self link."
  value       = google_compute_subnetwork.workloads.self_link
}

output "sql_instance_name" {
  description = "Cloud SQL instance name."
  value       = google_sql_database_instance.frontier.name
}

output "sql_connection_name" {
  description = "Cloud SQL connection name (project:region:instance) for the proxy/connector."
  value       = google_sql_database_instance.frontier.connection_name
}

output "sql_private_ip" {
  description = "Private IP of the Cloud SQL instance."
  value       = google_sql_database_instance.frontier.private_ip_address
}

output "database_name" {
  description = "Frontier database name."
  value       = google_sql_database.frontier.name
}

output "artifact_registry_repo" {
  description = "Artifact Registry Docker repository path."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}

output "crawler_service_account" {
  description = "Email of the crawler workload service account."
  value       = google_service_account.crawler.email
}

output "processing_service_account" {
  description = "Email of the Ray processing workload service account."
  value       = google_service_account.processing.email
}

output "secret_ids" {
  description = "Secret Manager secret IDs created by this module."
  value = {
    db_password           = google_secret_manager_secret.db_password.secret_id
    db_connection         = google_secret_manager_secret.db_connection.secret_id
    crawler_contact_email = google_secret_manager_secret.crawler_contact_email.secret_id
  }
}
