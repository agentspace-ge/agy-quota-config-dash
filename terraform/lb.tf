# ==============================================================================
# External Application Load Balancer with Cloud Run Serverless NEG & IAP
# Active when access_mode == "external_lb" or enable_lb == true (Stage 1 warmup)
# ==============================================================================

# 1. Global Static IPv4 Address for the Load Balancer
# Provisioned when provision_external_lb == true or retain_lb_ip == true.
# Note: prevent_destroy is intentionally omitted so switching back from external_lb
# to proxy mode (with enable_lb = false and retain_lb_ip = false) succeeds cleanly.
resource "google_compute_global_address" "lb_ip" {
  count      = local.provision_lb_ip ? 1 : 0
  project    = var.project_id
  name       = "antigravity-portal-ip"
  ip_version = "IPV4"

  depends_on = [google_project_service.apis]
}

# 2. Serverless Network Endpoint Group (NEG) pointing to the Cloud Run service
resource "google_compute_region_network_endpoint_group" "serverless_neg" {
  count                 = local.provision_external_lb ? 1 : 0
  project               = var.project_id
  region                = var.region
  name                  = "antigravity-portal-neg"
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = "antigravity-quota-portal"
  }
}

# 3. Global Backend Service with Identity-Aware Proxy (IAP) enabled
# When iap_oauth_client_id and iap_oauth_client_secret are empty, IAP uses its
# built-in Google-managed OAuth client after the Internal OAuth Consent Screen is configured.
resource "google_compute_backend_service" "portal_backend" {
  count                 = local.provision_external_lb ? 1 : 0
  project               = var.project_id
  name                  = "antigravity-portal-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"

  backend {
    group = google_compute_region_network_endpoint_group.serverless_neg[0].id
  }

  iap {
    enabled              = true
    oauth2_client_id     = var.iap_oauth_client_id != "" ? var.iap_oauth_client_id : null
    oauth2_client_secret = var.iap_oauth_client_secret != "" ? var.iap_oauth_client_secret : null
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# 4. IAP Web Backend Service IAM Members (roles/iap.httpsResourceAccessor)
resource "google_iap_web_backend_service_iam_member" "iap_members" {
  for_each = local.provision_external_lb ? toset(local.effective_iap_members) : toset([])

  project             = var.project_id
  web_backend_service = google_compute_backend_service.portal_backend[0].name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.value
}

# 5. Google-Managed SSL Certificate for custom domain, Cloud DNS zone, or sslip.io
resource "google_compute_managed_ssl_certificate" "lb_cert" {
  count    = local.provision_external_lb ? 1 : 0
  project  = var.project_id
  provider = google-beta
  name     = "antigravity-portal-cert-${substr(sha1(local.lb_hostname), 0, 8)}"

  managed {
    domains = [local.lb_hostname]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# 6. HTTPS URL Map routing all traffic to the backend service
resource "google_compute_url_map" "https_url_map" {
  count           = local.provision_external_lb ? 1 : 0
  project         = var.project_id
  name            = "antigravity-portal-url-map"
  default_service = google_compute_backend_service.portal_backend[0].id
}

# 7. HTTP URL Map redirecting all HTTP requests to HTTPS
resource "google_compute_url_map" "http_redirect_map" {
  count   = local.provision_external_lb ? 1 : 0
  project = var.project_id
  name    = "antigravity-portal-http-redirect"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

# 8. Target HTTPS Proxy
resource "google_compute_target_https_proxy" "https_proxy" {
  count            = local.provision_external_lb ? 1 : 0
  project          = var.project_id
  name             = "antigravity-portal-https-proxy"
  url_map          = google_compute_url_map.https_url_map[0].id
  ssl_certificates = [google_compute_managed_ssl_certificate.lb_cert[0].id]
}

# 9. Target HTTP Proxy
resource "google_compute_target_http_proxy" "http_proxy" {
  count   = local.provision_external_lb ? 1 : 0
  project = var.project_id
  name    = "antigravity-portal-http-proxy"
  url_map = google_compute_url_map.http_redirect_map[0].id
}

# 10. Global HTTPS Forwarding Rule (Port 443)
resource "google_compute_global_forwarding_rule" "https_forwarding_rule" {
  count                 = local.provision_external_lb ? 1 : 0
  project               = var.project_id
  name                  = "antigravity-portal-https-fr"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  target                = google_compute_target_https_proxy.https_proxy[0].id
  port_range            = "443"
  ip_address            = google_compute_global_address.lb_ip[0].address
}

# 11. Global HTTP Forwarding Rule (Port 80 -> HTTPS redirect)
resource "google_compute_global_forwarding_rule" "http_forwarding_rule" {
  count                 = local.provision_external_lb ? 1 : 0
  project               = var.project_id
  name                  = "antigravity-portal-http-fr"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  target                = google_compute_target_http_proxy.http_proxy[0].id
  port_range            = "80"
  ip_address            = google_compute_global_address.lb_ip[0].address
}
