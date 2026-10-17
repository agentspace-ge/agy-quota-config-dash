# ==============================================================================
# Google Cloud Storage (GCS) Staging Bucket for Vertex AI Agent Engine
# ==============================================================================

resource "google_storage_bucket" "concierge_staging" {
  count                       = var.enable_concierge_agent ? 1 : 0
  name                        = "${var.project_id}-agent-engine-staging"
  project                     = var.project_id
  location                    = var.concierge_agent_region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 30 # Auto-clean old deployment staging bundles after 30 days
    }
  }

  depends_on = [google_project_service.apis]
}

output "concierge_staging_bucket_url" {
  description = "GCS Staging Bucket URL for Vertex AI Agent Engine deployments."
  value       = var.enable_concierge_agent && length(google_storage_bucket.concierge_staging) > 0 ? google_storage_bucket.concierge_staging[0].url : ""
}
