variable "project_id" {
  type        = string
  description = "Google Cloud Project ID"
}

variable "region" {
  type        = string
  description = "GCP Region for Cloud Run, Artifact Registry, Firestore and BigQuery"
  default     = "us-east5"
}

variable "bigquery_dataset_name" {
  type        = string
  description = "BigQuery dataset name for exported Antigravity inference audit logs"
  default     = "antigravity_inference_logs"
}

variable "customer_id" {
  type        = string
  description = "The Google Workspace or Cloud Identity Customer ID (e.g. C04hbinmc) required to manage groups"
  default     = null
}

variable "manage_cloud_identity_groups" {
  type        = bool
  description = "Whether Terraform should manage the Cloud Identity groups, memberships, and project IAM role"
  default     = true
}

variable "enabled_group_email" {
  type        = string
  description = "Cloud Identity group email for active developers with roles/businessaicode.user"
}

variable "enabled_group_display_name" {
  type        = string
  description = "Display name for the Antigravity Enabled group"
  default     = "Antigravity Enabled Developers"
}

variable "enabled_group_description" {
  type        = string
  description = "Description for the Antigravity Enabled group"
  default     = "Developers with active Antigravity quota"
}

variable "disabled_group_email" {
  type        = string
  description = "Cloud Identity group email for throttled/locked developers"
}

variable "disabled_group_display_name" {
  type        = string
  description = "Display name for the Antigravity Throttled group"
  default     = "Antigravity Throttled Developers"
}

variable "disabled_group_description" {
  type        = string
  description = "Description for the Antigravity Throttled group"
  default     = "Developers temporarily throttled due to quota limits"
}

variable "app_timezone" {
  type        = string
  description = "Application timezone for weekly Monday 00:00 boundary calculation"
  default     = "America/Los_Angeles"
}

variable "default_quota_usd" {
  type        = number
  description = "Default weekly developer quota credit allocation in USD"
  default     = 10.00
}

variable "default_overage_usd" {
  type        = number
  description = "Default weekly developer overage buffer before auto-throttling in USD"
  default     = 2.00
}

variable "image_tag" {
  type        = string
  description = "Docker image tag to deploy to Cloud Run"
  default     = "latest"
}

variable "domain_override" {
  type        = string
  description = "Optional custom public hostname for the LB. If empty, derives a sslip.io hostname from the static IP."
  default     = ""
}

variable "iap_oauth_client_id" {
  type        = string
  description = "OAuth 2.0 Client ID for Identity-Aware Proxy (IAP)"
  default     = ""
}

variable "iap_oauth_client_secret" {
  type        = string
  description = "OAuth 2.0 Client Secret for Identity-Aware Proxy (IAP)"
  default     = ""
  sensitive   = true
}

variable "access_mode" {
  type        = string
  description = "Cloud Run access and ingress mode. Options: 'proxy' (Private Cloud Run with IAM Authenticated Proxy Bridge, ideal for Argolis/Cloud Shell), 'internal_lb' (Regional Internal Application Load Balancer via Serverless NEG on private VPC), 'external_lb' (External HTTPS Load Balancer with IAP), or 'direct' (Direct Cloud Run URL)."
  default     = "proxy"

  validation {
    condition     = contains(["proxy", "internal_lb", "external_lb", "direct"], var.access_mode)
    error_message = "access_mode must be one of: 'proxy', 'internal_lb', 'external_lb', 'direct'."
  }
}

variable "proxy_ingress_type" {
  type        = string
  description = "Ingress level for 'proxy' access_mode: 'internal' (strictly internal VPC/bastion only) or 'all' (IAM-authenticated default ingress, allows gcloud run services proxy directly from workstations with --no-allow-unauthenticated)."
  default     = "all"

  validation {
    condition     = contains(["internal", "all"], var.proxy_ingress_type)
    error_message = "proxy_ingress_type must be either 'internal' or 'all'."
  }
}

variable "argolis_tenant_domain" {
  type        = string
  description = "Argolis demo environment tenant domain (e.g., 'gcp.altostrat.com' or '<tenant>.altostrat.com'). Automatically binds domain:<domain> to roles/run.invoker on Cloud Run."
  default     = "gcp.altostrat.com"
}

variable "argolis_allowed_invokers" {
  type        = list(string)
  description = "Additional IAM identities granted roles/run.invoker on Cloud Run (e.g., 'user:demo-admin@gcp.altostrat.com', 'group:admins@gcp.altostrat.com')."
  default     = []
}

variable "vpc_network" {
  type        = string
  description = "VPC network name for Regional Internal Application Load Balancer (used when access_mode = 'internal_lb')."
  default     = "default"
}

variable "vpc_subnet" {
  type        = string
  description = "VPC subnetwork name for Regional Internal Application Load Balancer forwarding rule (used when access_mode = 'internal_lb')."
  default     = "default"
}

variable "create_proxy_only_subnet" {
  type        = bool
  description = "Whether to create a regional proxy-only subnet for the Regional Internal ALB. Set to false if the VPC already has a REGIONAL_MANAGED_PROXY subnet in the target region."
  default     = false
}

variable "proxy_only_subnet_name" {
  type        = string
  description = "Name for the regional proxy-only subnet when create_proxy_only_subnet is true."
  default     = "antigravity-portal-proxy-subnet"
}

variable "proxy_only_subnet_cidr" {
  type        = string
  description = "CIDR range for the regional proxy-only subnet (e.g. 10.128.0.0/23)."
  default     = "10.128.0.0/23"
}

variable "create_internal_firewall_rule" {
  type        = bool
  description = "Whether to create a VPC firewall rule allowing ingress traffic to the internal load balancer."
  default     = false
}

variable "internal_firewall_source_ranges" {
  type        = list(string)
  description = "Source CIDR ranges allowed to access the internal load balancer if create_internal_firewall_rule is true."
  default     = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
}

variable "enable_lb" {
  type        = bool
  description = "Legacy flag: Enable provisioning the full External Application Load Balancer + IAP stack. Overridden if access_mode is set."
  default     = false
}

variable "iap_allowed_members" {
  type        = list(string)
  description = "List of members (e.g. domain:example.com, user:foo@example.com) granted roles/iap.httpsResourceAccessor on the web backend service."
  default     = []
}

