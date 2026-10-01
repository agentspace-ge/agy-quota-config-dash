# ==============================================================================
# Common Locals for Ingress, Argolis Access Modes & IAM
# ==============================================================================

locals {
  is_internal_lb = var.access_mode == "internal_lb"
  is_proxy       = var.access_mode == "proxy"
  is_external_lb = var.access_mode == "external_lb" || (var.enable_lb && var.access_mode != "proxy" && var.access_mode != "internal_lb")

  # Ingress traffic control rule:
  # - proxy: INGRESS_TRAFFIC_INTERNAL_ONLY (accessed securely via gcloud run services proxy)
  # - internal_lb: INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER (accessed via Regional Internal ALB / VPC Serverless NEG)
  # - external_lb: INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER (accessed via External HTTPS ALB + IAP)
  # - direct: INGRESS_TRAFFIC_ALL
  cloud_run_ingress = (
    local.is_proxy ? (var.proxy_ingress_type == "internal" ? "INGRESS_TRAFFIC_INTERNAL_ONLY" : "INGRESS_TRAFFIC_ALL") :
    local.is_internal_lb ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" :
    local.is_external_lb ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" :
    "INGRESS_TRAFFIC_ALL"
  )

  # Derive Argolis domain invoker binding if argolis_tenant_domain is specified
  tenant_domain_invoker = var.argolis_tenant_domain != "" ? ["domain:${var.argolis_tenant_domain}"] : []
  effective_invokers    = distinct(concat(var.argolis_allowed_invokers, local.tenant_domain_invoker))

  # External Load Balancer hostname derived from global static IP or custom override
  lb_hostname = var.domain_override != "" ? var.domain_override : (
    length(google_compute_global_address.lb_ip) > 0 ? "${replace(google_compute_global_address.lb_ip[0].address, ".", "-")}.sslip.io" : ""
  )

  # Fully qualified Docker container image URI in Artifact Registry
  container_image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker_repo.repository_id}/app:${var.image_tag}"
}
