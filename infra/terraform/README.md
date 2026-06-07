# Food-Crawl GCP Foundation (Terraform)

Milestone 1 infrastructure for the Chicago restaurant food-blog corpus platform.
This module provisions the shared foundation every downstream component depends on:

- **Project APIs** — enables Compute, Cloud SQL, Storage, Secret Manager, Artifact
  Registry, GKE, Cloud Composer, Monitoring, Logging, and Service Networking.
- **Networking** — custom-mode VPC, a workload subnet (with secondary ranges for
  GKE pods/services), Cloud Router + NAT for egress, internal/health-check
  firewall rules, and Private Service Access for Cloud SQL.
- **GCS buckets** — the five medallion zones `raw`, `bronze`, `silver`, `gold`,
  `train` (uniform access, public access blocked, object versioning).
- **Cloud SQL (Postgres)** — private-IP `frontier` instance, database, and app
  user for the URL frontier.
- **Artifact Registry** — Docker repository for crawler and Ray job images.
- **Secret Manager** — DB password, full DB connection JSON, and crawler contact
  email.
- **IAM** — two least-privilege workload service accounts (`crawler`,
  `processing`) with the bucket/Cloud SQL/secret access each needs.

> Note: GKE clusters, Ray, and Cloud Composer environments themselves are created
> in later milestones. This module enables their APIs and lays the network/IAM
> groundwork.

## Prerequisites

- Terraform `>= 1.5`
- `gcloud` CLI authenticated with rights to manage the target project
- A GCP project with billing enabled
- Application Default Credentials:

```bash
gcloud auth application-default login
gcloud config set project <PROJECT_ID>
```

## Bootstrap remote state

The backend bucket must exist before `terraform init` (Terraform can't store its
own state in a bucket it hasn't created yet). Create it once per project:

```bash
PROJECT_ID=<PROJECT_ID>
STATE_BUCKET=${PROJECT_ID}-tfstate

gcloud storage buckets create gs://${STATE_BUCKET} \
  --project="${PROJECT_ID}" \
  --location=US \
  --uniform-bucket-level-access
gcloud storage buckets update gs://${STATE_BUCKET} --versioning
```

Then create your backend config:

```bash
cp backend.hcl.example backend.hcl
# edit backend.hcl: set bucket = "<PROJECT_ID>-tfstate"
```

## Configure variables

```bash
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: set project_id (and any overrides)
```

## Plan & apply

```bash
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

First apply may take ~10–15 minutes (Cloud SQL + Service Networking are the slow
parts). To inspect outputs afterwards:

```bash
terraform output
terraform output -json bucket_names
```

## Notes & gotchas

- **Bucket names are global.** By default buckets are named
  `<project_id>-chi-food-<zone>` to avoid collisions. Override `bucket_prefix`
  only if you own the exact names (e.g. `chi-food`).
- **Cloud SQL has no public IP.** Connect from inside the VPC, via the Cloud SQL
  Auth Proxy, or the Cloud SQL connector using `sql_connection_name`.
- **`db_deletion_protection` defaults to `true`.** Set it to `false` (and re-apply)
  before `terraform destroy` will remove the instance.
- **Secrets** are stored in Secret Manager; the generated DB password is also in
  Terraform state, so keep the state bucket locked down.
- Destroying buckets that contain objects requires emptying them first (no
  `force_destroy` is set, to protect raw data).

## Key outputs

| Output | Description |
| ------ | ----------- |
| `bucket_names` / `bucket_urls` | Medallion zone → bucket name / `gs://` URL |
| `sql_connection_name` | `project:region:instance` for the proxy/connector |
| `sql_private_ip` | Private IP of the frontier DB |
| `artifact_registry_repo` | Docker repo path for pushes |
| `crawler_service_account` / `processing_service_account` | Workload SA emails |
| `secret_ids` | Secret Manager secret IDs |
