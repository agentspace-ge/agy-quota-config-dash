# ==============================================================================
# Regional Internal Application Load Balancer (Internal ALB) with Serverless NEG
# Active when access_mode == "internal_lb"
# Provides private, VPC-internal ingress without public internet exposure
# ==============================================================================

# 1. Serverless Network Endpoint Group (NEG) pointing to the Cloud Run service
resource "google_compute_region_network_endpoint_group" "internal_serverless_neg" {
  count                 = local.is_internal_lb ? 1 : 0
  project               = var.project_id
  region                = var.region
  name                  = "antigravity-portal-internal-neg"
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.portal_service.name
  }

  depends_on = [google_project_service.apis]
}

# 2. Regional Backend Service for the Internal Application Load Balancer
resource "google_compute_region_backend_service" "internal_portal_backend" {
  count                 = local.is_internal_lb ? 1 : 0
  project               = var.project_id
  region                = var.region
  name                  = "antigravity-portal-internal-backend"
  load_balancing_scheme = "INTERNAL_MANAGED"
  protocol              = "HTTP"

  backend {
    group = google_compute_region_network_endpoint_group.internal_serverless_neg[0].id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }

  depends_on = [google_project_service.apis]
}

# 3. Regional URL Map routing internal requests to the regional backend service
resource "google_compute_region_url_map" "internal_url_map" {
  count           = local.is_internal_lb ? 1 : 0
  project         = var.project_id
  region          = var.region
  name            = "antigravity-portal-internal-url-map"
  default_service = google_compute_region_backend_service.internal_portal_backend[0].id

  depends_on = [google_project_service.apis]
}

# 4. Regional Target HTTP Proxy
resource "google_compute_region_target_http_proxy" "internal_http_proxy" {
  count   = local.is_internal_lb ? 1 : 0
  project = var.project_id
  region  = var.region
  name    = "antigravity-portal-internal-http-proxy"
  url_map = google_compute_region_url_map.internal_url_map[0].id

  depends_on = [google_project_service.apis]
}

# 5. Regional Internal Forwarding Rule on a private VPC subnet
resource "google_compute_forwarding_rule" "internal_forwarding_rule" {
  count                 = local.is_internal_lb ? 1 : 0
  project               = var.project_id
  region                = var.region
  name                  = "antigravity-portal-internal-fr"
  load_balancing_scheme = "INTERNAL_MANAGED"
  network               = var.vpc_network
  subnetwork            = var.vpc_subnet
  ip_protocol           = "TCP"
  port_range            = "80"
  target                = google_compute_region_target_http_proxy.internal_http_proxy[0].id

  depends_on = [
    google_project_service.apis,
    google_compute_subnetwork.proxy_only_subnet
  ]
}

# 6. Optional Regional Proxy-Only Subnet (required by GCP for Regional Internal ALBs if one does not exist)
resource "google_compute_subnetwork" "proxy_only_subnet" {
  count         = (local.is_internal_lb && var.create_proxy_only_subnet) ? 1 : 0
  name          = var.proxy_only_subnet_name != "" ? var.proxy_only_subnet_name : "antigravity-portal-proxy-subnet"
  project       = var.project_id
  region        = var.region
  ip_cidr_range = var.proxy_only_subnet_cidr
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
  network       = var.vpc_network

  depends_on = [google_project_service.apis]
}

# 7. Optional VPC Firewall Rule allowing traffic to the Internal Load Balancer
resource "google_compute_firewall" "allow_internal_lb" {
  count     = (local.is_internal_lb && var.create_internal_firewall_rule) ? 1 : 0
  project   = var.project_id
  name      = "antigravity-portal-allow-internal-lb"
  network   = var.vpc_network
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = var.internal_firewall_source_ranges

  depends_on = [google_project_service.apis]
}
