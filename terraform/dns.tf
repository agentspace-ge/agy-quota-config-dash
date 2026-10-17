# ==============================================================================
# Cloud DNS Managed Zone & A-Record Configuration for External Load Balancer
# Supports both creating a new Cloud DNS zone (manage_dns_zone = true) and
# referencing an existing pre-delegated Cloud DNS zone (manage_dns_zone = false).
# ==============================================================================

locals {
  has_dns_zone_config = local.provision_lb_ip && local.normalized_dns_zone_domain != "" && var.dns_zone_name != ""
}

# 1. Optional Terraform-Managed Cloud DNS Public Zone (when manage_dns_zone == true)
resource "google_dns_managed_zone" "lb_zone" {
  count         = local.has_dns_zone_config && var.manage_dns_zone ? 1 : 0
  project       = local.effective_dns_project_id
  name          = var.dns_zone_name
  dns_name      = "${local.normalized_dns_zone_domain}."
  description   = "Public Cloud DNS zone for Antigravity Quota Portal External Load Balancer"
  visibility    = "public"
  force_destroy = true

  depends_on = [google_project_service.apis]
}

# 2. Existing Pre-Delegated Cloud DNS Public Zone Lookup (when manage_dns_zone == false)
data "google_dns_managed_zone" "existing_lb_zone" {
  count   = local.has_dns_zone_config && !var.manage_dns_zone ? 1 : 0
  project = local.effective_dns_project_id
  name    = var.dns_zone_name
}

# 3. Public DNS A-Record pointing the configured FQDN to the Global Static IPv4 Address
resource "google_dns_record_set" "lb_a_record" {
  count        = local.has_dns_zone_config ? 1 : 0
  project      = local.effective_dns_project_id
  managed_zone = var.manage_dns_zone ? google_dns_managed_zone.lb_zone[0].name : data.google_dns_managed_zone.existing_lb_zone[0].name
  name         = "${local.dns_fqdn}."
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_global_address.lb_ip[0].address]
}
