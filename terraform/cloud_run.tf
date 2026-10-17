# Artifact Registry Docker repository
resource "google_artifact_registry_repository" "docker_repo" {
  repository_id = "antigravity-portal"
  format        = "DOCKER"
  project       = var.project_id
  location      = var.region
  description   = "Docker repository for Antigravity Quota Portal container images"

  depends_on = [google_project_service.apis]
}

# Cloud Run v2 Service (Always-On min=1, max=1)
resource "google_cloud_run_v2_service" "portal_service" {
  name     = "antigravity-quota-portal"
  location = var.region
  project  = var.project_id

  ingress = local.cloud_run_ingress

  template {
    service_account = google_service_account.portal_sa.email

    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    containers {
      image = local.container_image

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "REGION"
        value = var.region
      }
      env {
        name  = "BIGQUERY_DATASET"
        value = google_bigquery_dataset.audit_dataset.dataset_id
      }
      env {
        name  = "ENABLED_GROUP_EMAIL"
        value = var.enabled_group_email
      }
      env {
        name  = "DISABLED_GROUP_EMAIL"
        value = var.disabled_group_email
      }
      env {
        name  = "APP_TIMEZONE"
        value = var.app_timezone
      }
      env {
        name  = "DEFAULT_QUOTA_USD"
        value = tostring(var.default_quota_usd)
      }
      env {
        name  = "DEFAULT_OVERAGE_USD"
        value = tostring(var.default_overage_usd)
      }
      env {
        name  = "USE_MOCK_SERVICES"
        value = "false"
      }
      env {
        name  = "CONCIERGE_SERVICE_ACCOUNT_EMAIL"
        value = local.effective_concierge_sa_email
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_firestore_database.database,
    google_bigquery_dataset.audit_dataset,
    google_project_iam_member.bq_job_user,
    google_bigquery_dataset_iam_member.bq_data_viewer,
    google_project_iam_member.firestore_user,
    google_project_iam_member.logging_log_writer,
    terraform_data.cloud_build_image
  ]
}

# IAP Service Agent Identity (provisioned when External ALB with IAP is enabled or warming up)
resource "google_project_service_identity" "iap_sa" {
  count    = local.provision_external_lb ? 1 : 0
  provider = google-beta
  project  = var.project_id
  service  = "iap.googleapis.com"
}

# Grant Cloud Run Invoker to IAP Service Agent so the External Load Balancer can route requests to Cloud Run
resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  count    = local.provision_external_lb ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = "antigravity-quota-portal"
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_project_service_identity.iap_sa[0].email}"
}

# Authorized IAM Invokers
# Strictly enforces --no-allow-unauthenticated by granting roles/run.invoker
# exclusively to authorized organization domain/group/user identities.
resource "google_cloud_run_v2_service_iam_member" "authorized_invokers" {
  for_each = toset(local.effective_invokers)

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.portal_service.name
  role     = "roles/run.invoker"
  member   = each.value
}

# Grant Cloud Run Invoker to the Antigravity Quota Concierge Agent Engine Service Account (when enabled or provided)
resource "google_cloud_run_v2_service_iam_member" "concierge_invoker" {
  count    = local.effective_concierge_sa_email != "" ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.portal_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.effective_concierge_sa_email}"
}

