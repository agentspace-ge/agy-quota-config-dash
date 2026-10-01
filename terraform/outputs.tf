output "cloud_run_url" {
  description = "Direct URL of the deployed Antigravity Quota Portal Cloud Run service"
  value       = google_cloud_run_v2_service.portal_service.uri
}

output "service_account_email" {
  description = "Dedicated Service Account email used by Cloud Run"
  value       = google_service_account.portal_sa.email
}

output "bigquery_dataset_id" {
  description = "BigQuery dataset ID for inference audit logs"
  value       = google_bigquery_dataset.audit_dataset.dataset_id
}

output "artifact_registry_repository" {
  description = "Artifact Registry Docker repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker_repo.repository_id}"
}

output "cloud_logging_sink_writer_identity" {
  description = "Service Account identity used by Cloud Logging Log Router Sink"
  value       = google_logging_project_sink.antigravity_sink.writer_identity
}

output "access_mode" {
  description = "Active Cloud Run ingress and access governance mode"
  value       = var.access_mode
}

output "cloud_run_ingress" {
  description = "Configured Cloud Run v2 ingress traffic setting"
  value       = local.cloud_run_ingress
}

output "lb_ip_address" {
  description = "Global Static IPv4 address reserved for External Load Balancer (when access_mode is external_lb)"
  value       = local.is_external_lb ? google_compute_global_address.lb_ip[0].address : null
}

output "lb_hostname" {
  description = "Public hostname derived via sslip.io or domain override (when access_mode is external_lb)"
  value       = local.is_external_lb ? local.lb_hostname : null
}

output "iap_oauth_redirect_uri" {
  description = "Authorized redirect URI to register in the Google Cloud Console OAuth 2.0 Web Client credentials"
  value       = local.is_external_lb ? (var.iap_oauth_client_id != "" ? "https://iap.googleapis.com/v1/oauth/clientIds/${var.iap_oauth_client_id}:handleRedirect" : "https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect") : null
}

output "internal_lb_ip" {
  description = "Internal IP address of the Regional Internal Application Load Balancer forwarding rule (when access_mode is internal_lb)"
  value       = local.is_internal_lb ? google_compute_forwarding_rule.internal_forwarding_rule[0].ip_address : null
}

output "proxy_command" {
  description = "Command to establish an authenticated proxy bridge to the private Cloud Run service"
  value       = "gcloud run services proxy ${google_cloud_run_v2_service.portal_service.name} --port=8080 --region=${var.region} --project=${var.project_id}"
}

output "argolis_invokers" {
  description = "List of authorized IAM identities bound to roles/run.invoker"
  value       = local.effective_invokers
}

output "portal_url" {
  description = "Active portal URL or access instructions based on access_mode"
  value = (
    local.is_external_lb ? "https://${local.lb_hostname}" :
    local.is_internal_lb ? "http://${google_compute_forwarding_rule.internal_forwarding_rule[0].ip_address}" :
    local.is_proxy ? "http://localhost:8080 (Run: ./scripts/argolis_access.sh proxy)" :
    google_cloud_run_v2_service.portal_service.uri
  )
}
