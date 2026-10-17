# ==============================================================================
# Common Locals for Ingress, Access Modes & IAM
# ==============================================================================

locals {
  is_internal_lb = var.access_mode == "internal_lb"
  is_proxy       = var.access_mode == "proxy"
  is_external_lb = var.access_mode == "external_lb"

  # Decouple GCLB + DNS + Managed SSL + IAP provisioning from Cloud Run ingress lockdown:
  # - provision_external_lb: true when access_mode == "external_lb" OR enable_lb == true (Stage 1 warmup / warm rollback)
  # - provision_lb_ip: true when provision_external_lb == true OR retain_lb_ip == true (keeps Global Static IP + DNS record)
  provision_external_lb = local.is_external_lb || var.enable_lb
  provision_lb_ip       = local.provision_external_lb || var.retain_lb_ip

  # Ingress traffic control rule:
  # - proxy: INGRESS_TRAFFIC_ALL (default) or INGRESS_TRAFFIC_INTERNAL_ONLY (accessed via gcloud run services proxy)
  # - internal_lb: INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER (accessed via Regional Internal ALB / VPC Serverless NEG)
  # - external_lb: INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER (or INGRESS_TRAFFIC_ALL when allow_proxy_with_lb == true)
  # - direct: INGRESS_TRAFFIC_ALL
  cloud_run_ingress = (
    local.is_proxy ? (var.proxy_ingress_type == "internal" ? "INGRESS_TRAFFIC_INTERNAL_ONLY" : "INGRESS_TRAFFIC_ALL") :
    local.is_internal_lb ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" :
    local.is_external_lb ? (var.allow_proxy_with_lb ? "INGRESS_TRAFFIC_ALL" : "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER") :
    "INGRESS_TRAFFIC_ALL"
  )

  # Derive organization domain invoker binding if tenant_domain is specified
  tenant_domain_invoker = var.tenant_domain != "" ? ["domain:${var.tenant_domain}"] : []
  effective_invokers    = distinct(concat(var.allowed_invokers, local.tenant_domain_invoker))

  # Cloud DNS configuration (supports new or existing delegated zone, plus optional subdomain prefix)
  effective_dns_project_id   = var.dns_project_id != "" ? var.dns_project_id : var.project_id
  normalized_dns_zone_domain = trimsuffix(trimspace(var.dns_zone_domain), ".")
  normalized_dns_prefix      = trim(trimspace(var.dns_record_prefix), ".")
  dns_fqdn = local.normalized_dns_zone_domain != "" ? (
    local.normalized_dns_prefix != "" ? "${local.normalized_dns_prefix}.${local.normalized_dns_zone_domain}" : local.normalized_dns_zone_domain
  ) : ""

  # External Load Balancer hostname precedence:
  # 1. Explicit domain_override
  # 2. Cloud DNS FQDN (dns_record_prefix + dns_zone_domain)
  # 3. Derived <LB_IP>.sslip.io from the Global Static IPv4 address
  lb_hostname = var.domain_override != "" ? var.domain_override : (
    local.dns_fqdn != "" ? local.dns_fqdn : (
      length(google_compute_global_address.lb_ip) > 0 ? "${replace(google_compute_global_address.lb_ip[0].address, ".", "-")}.sslip.io" : ""
    )
  )

  # Fully qualified Docker container image URI in Artifact Registry
  container_image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker_repo.repository_id}/antigravity-quota-portal:${var.image_tag}"

  # Effective Concierge Agent Service Account email (in-project or cross-project)
  effective_concierge_sa_email = (
    var.concierge_service_account_email != "" ? var.concierge_service_account_email : (
      var.enable_concierge_agent && length(google_service_account.concierge_sa) > 0 ? google_service_account.concierge_sa[0].email : ""
    )
  )

  # Automated IAP Backend Service IAM members (roles/iap.httpsResourceAccessor)
  # Combines tenant domain + allowed invokers + explicit iap_allowed_members + Concierge SA + Reasoning Engine Service Agent
  concierge_iap_members = concat(
    local.effective_concierge_sa_email != "" ? ["serviceAccount:${local.effective_concierge_sa_email}"] : [],
    var.enable_concierge_agent ? ["serviceAccount:service-${data.google_project.project.number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"] : []
  )
  effective_iap_members = distinct(concat(
    local.effective_invokers,
    var.iap_allowed_members,
    local.concierge_iap_members
  ))
}
