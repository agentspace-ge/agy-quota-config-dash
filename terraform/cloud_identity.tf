# ==============================================================================
# Cloud Identity Groups & Dual-Group Governance Automation
# Provisions the required 'antigravity-enabled' and 'antigravity-disabled' groups
# and configures Service Account ownership & IAM role bindings.
# ==============================================================================

# Antigravity Enabled Developers Group
resource "google_cloud_identity_group" "enabled_group" {
  count = var.manage_cloud_identity_groups && var.customer_id != null && var.customer_id != "" ? 1 : 0

  display_name = var.enabled_group_display_name
  description  = var.enabled_group_description
  parent       = "customers/${var.customer_id}"

  group_key {
    id = var.enabled_group_email
  }

  labels = {
    "cloudidentity.googleapis.com/groups.discussion_forum" = ""
  }

  initial_group_config = "WITH_INITIAL_OWNER"

  depends_on = [
    google_project_service.apis["cloudidentity.googleapis.com"]
  ]
}

# Antigravity Throttled (Disabled) Developers Group
resource "google_cloud_identity_group" "disabled_group" {
  count = var.manage_cloud_identity_groups && var.customer_id != null && var.customer_id != "" ? 1 : 0

  display_name = var.disabled_group_display_name
  description  = var.disabled_group_description
  parent       = "customers/${var.customer_id}"

  group_key {
    id = var.disabled_group_email
  }

  labels = {
    "cloudidentity.googleapis.com/groups.discussion_forum" = ""
  }

  initial_group_config = "WITH_INITIAL_OWNER"

  depends_on = [
    google_project_service.apis["cloudidentity.googleapis.com"]
  ]
}

# Ensure Cloud Run service account is OWNER in the enabled group
resource "google_cloud_identity_group_membership" "portal_sa_enabled_membership" {
  count = var.manage_cloud_identity_groups && var.customer_id != null && var.customer_id != "" ? 1 : 0

  group = google_cloud_identity_group.enabled_group[0].name

  preferred_member_key {
    id = google_service_account.portal_sa.email
  }

  roles {
    name = "MEMBER"
  }

  roles {
    name = "OWNER"
  }

  create_ignore_already_exists = true

  depends_on = [
    google_cloud_identity_group.enabled_group,
    google_service_account.portal_sa
  ]
}

# Ensure Cloud Run service account is OWNER in the disabled group
resource "google_cloud_identity_group_membership" "portal_sa_disabled_membership" {
  count = var.manage_cloud_identity_groups && var.customer_id != null && var.customer_id != "" ? 1 : 0

  group = google_cloud_identity_group.disabled_group[0].name

  preferred_member_key {
    id = google_service_account.portal_sa.email
  }

  roles {
    name = "MEMBER"
  }

  roles {
    name = "OWNER"
  }

  create_ignore_already_exists = true

  depends_on = [
    google_cloud_identity_group.disabled_group,
    google_service_account.portal_sa
  ]
}

# Grant roles/businessaicode.user to the enabled group on the GCP project
resource "google_project_iam_member" "enabled_group_businessaicode_user" {
  count = var.manage_cloud_identity_groups ? 1 : 0

  project = var.project_id
  role    = "roles/businessaicode.user"
  member  = "group:${var.enabled_group_email}"

  depends_on = [
    google_cloud_identity_group.enabled_group
  ]
}
