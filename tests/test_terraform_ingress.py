"""Tests for private Cloud Run zero-trust ingress configuration and helper automation."""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TF_DIR = REPO_ROOT / "terraform"
SCRIPTS_DIR = REPO_ROOT / "scripts"


def test_terraform_files_exist():
    """Verify all required Terraform configuration files are present."""
    required_files = [
        "main.tf",
        "locals.tf",
        "cloud_identity.tf",
        "cloud_run.tf",
        "dns.tf",
        "internal_lb.tf",
        "lb.tf",
        "variables.tf",
        "outputs.tf",
        "terraform.tfvars.example",
    ]
    for filename in required_files:
        path = TF_DIR / filename
        assert path.exists(), f"Missing required terraform file: {filename}"


def test_variables_configuration():
    """Verify variables.tf defines access_mode, Cloud DNS, IAP, and mode-switching variables."""
    variables_content = (TF_DIR / "variables.tf").read_text()
    tfvars_example = (TF_DIR / "terraform.tfvars.example").read_text()

    for var_name in [
        "access_mode",
        "tenant_domain",
        "allowed_invokers",
        "vpc_network",
        "vpc_subnet",
        "create_proxy_only_subnet",
        "manage_dns_zone",
        "dns_project_id",
        "dns_zone_name",
        "dns_zone_domain",
        "dns_record_prefix",
        "allow_proxy_with_lb",
        "retain_lb_ip",
    ]:
        assert f'variable "{var_name}"' in variables_content, f"Missing variable {var_name} in variables.tf"
        if var_name not in ("access_mode", "tenant_domain", "allowed_invokers", "vpc_network", "vpc_subnet", "create_proxy_only_subnet"):
            assert var_name in tfvars_example, f"Missing {var_name} in terraform.tfvars.example"

    assert '"proxy"' in variables_content
    assert '"internal_lb"' in variables_content
    assert '"external_lb"' in variables_content


def test_dns_and_gclb_iap_warmup_and_rollback():
    """Verify Cloud DNS resources, 2-phase warmup locals, optional IAP OAuth, and clean rollback without prevent_destroy."""
    main_content = (TF_DIR / "main.tf").read_text()
    locals_content = (TF_DIR / "locals.tf").read_text()
    dns_content = (TF_DIR / "dns.tf").read_text()
    lb_content = (TF_DIR / "lb.tf").read_text()
    outputs_content = (TF_DIR / "outputs.tf").read_text()

    # 1. Verify Cloud DNS API and project data source in main.tf
    assert '"dns.googleapis.com"' in main_content
    assert 'data "google_project" "project"' in main_content

    # 2. Verify 2-phase warmup, retain_lb_ip, allow_proxy_with_lb, and automated IAP IAM in locals.tf
    assert "provision_external_lb = local.is_external_lb || var.enable_lb" in locals_content
    assert "provision_lb_ip       = local.provision_external_lb || var.retain_lb_ip" in locals_content
    assert 'var.allow_proxy_with_lb ? "INGRESS_TRAFFIC_ALL" : "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"' in locals_content
    assert "effective_iap_members" in locals_content
    assert "gcp-sa-aiplatform-re.iam.gserviceaccount.com" in locals_content

    # 3. Verify Cloud DNS Managed Zone (new or existing) and A-record in dns.tf
    assert 'resource "google_dns_managed_zone" "lb_zone"' in dns_content
    assert 'data "google_dns_managed_zone" "existing_lb_zone"' in dns_content
    assert 'resource "google_dns_record_set" "lb_a_record"' in dns_content

    # 4. Verify lb.tf does NOT have prevent_destroy = true (so switching external_lb -> proxy succeeds)
    assert "prevent_destroy = true" not in lb_content
    assert "count      = local.provision_lb_ip ? 1 : 0" in lb_content
    assert 'var.iap_oauth_client_id != "" ? var.iap_oauth_client_id : null' in lb_content
    assert 'var.iap_oauth_client_secret != "" ? var.iap_oauth_client_secret : null' in lb_content
    assert "toset(local.effective_iap_members)" in lb_content

    # 5. Verify outputs.tf exposes dns_name_servers and iap_allowed_members_effective
    assert 'output "dns_name_servers"' in outputs_content
    assert 'output "iap_allowed_members_effective"' in outputs_content


def test_cloud_run_ingress_and_iam():
    """Verify Cloud Run v2 enforces --no-allow-unauthenticated and dynamic ingress."""
    cloud_run_content = (TF_DIR / "cloud_run.tf").read_text()
    assert "ingress = local.cloud_run_ingress" in cloud_run_content
    assert 'resource "google_cloud_run_v2_service_iam_member" "authorized_invokers"' in cloud_run_content
    assert "roles/run.invoker" in cloud_run_content
    # Confirm no allUsers binding exists in any terraform file
    for tf_file in TF_DIR.glob("*.tf"):
        content = tf_file.read_text()
        assert "allUsers" not in content, (
            f"allUsers found in {tf_file.name} - unauthenticated access must be strictly forbidden"
        )



def test_internal_lb_resources():
    """Verify internal_lb.tf declares Regional Internal ALB with Serverless NEG."""
    internal_lb_content = (TF_DIR / "internal_lb.tf").read_text()
    assert "google_compute_region_network_endpoint_group" in internal_lb_content
    assert "SERVERLESS" in internal_lb_content
    assert "google_compute_region_backend_service" in internal_lb_content
    assert "INTERNAL_MANAGED" in internal_lb_content
    assert "google_compute_region_url_map" in internal_lb_content
    assert "google_compute_region_target_http_proxy" in internal_lb_content
    assert "google_compute_forwarding_rule" in internal_lb_content


def test_portal_access_script():
    """Verify scripts/portal_access.sh is executable and provides help/proxy/token."""
    script_path = SCRIPTS_DIR / "portal_access.sh"
    assert script_path.exists(), "scripts/portal_access.sh does not exist"
    assert os.access(script_path, os.X_OK), "scripts/portal_access.sh must be executable"

    script_content = script_path.read_text()
    assert "gcloud run services proxy" in script_content
    assert "gcloud auth print-identity-token" in script_content

    # Run help command to verify shell syntax and execution
    result = subprocess.run(
        [str(script_path), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Usage: ./scripts/portal_access.sh" in result.stdout
    assert "proxy" in result.stdout
    assert "token" in result.stdout
    assert "curl" in result.stdout
    assert "status" in result.stdout
    assert "dns-check" in result.stdout
    assert "iap-status" in result.stdout
    assert "iap-curl" in result.stdout
    assert "switch-mode" in result.stdout

    # Verify switch-mode rejects missing or invalid mode arguments cleanly
    missing_mode = subprocess.run(
        [str(script_path), "switch-mode"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing_mode.returncode != 0
    assert "requires a target mode" in missing_mode.stderr

    invalid_mode = subprocess.run(
        [str(script_path), "switch-mode", "invalid_mode"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid_mode.returncode != 0
    assert "Invalid mode 'invalid_mode'" in invalid_mode.stderr


def test_cloud_identity_terraform():
    """Verify cloud_identity.tf provisions groups, SA ownership, and IAM role bindings."""
    ci_content = (TF_DIR / "cloud_identity.tf").read_text()
    assert 'resource "google_cloud_identity_group" "enabled_group"' in ci_content
    assert 'resource "google_cloud_identity_group" "disabled_group"' in ci_content
    assert 'resource "google_cloud_identity_group_membership" "portal_sa_enabled_membership"' in ci_content
    assert 'resource "google_cloud_identity_group_membership" "portal_sa_disabled_membership"' in ci_content
    assert 'resource "google_project_iam_member" "enabled_group_businessaicode_user"' in ci_content
    assert '"roles/businessaicode.user"' in ci_content
    assert 'name = "OWNER"' in ci_content

    # Verify variables
    variables_content = (TF_DIR / "variables.tf").read_text()
    assert 'variable "customer_id"' in variables_content
    assert 'variable "manage_cloud_identity_groups"' in variables_content
