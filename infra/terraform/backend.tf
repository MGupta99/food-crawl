# Remote state in GCS. The state bucket must exist before `terraform init`.
# It is created out-of-band (see README "Bootstrap remote state") because a
# backend cannot use variables and Terraform cannot manage the bucket that
# holds its own state during init.
#
# Initialize with a partial backend config:
#   terraform init -backend-config=backend.hcl
#
# See backend.hcl.example for the expected keys.
terraform {
  backend "gcs" {}
}
