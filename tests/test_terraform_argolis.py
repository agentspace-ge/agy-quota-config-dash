"""Tests for Argolis private Cloud Run configuration and helper automation."""

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
        "internal_lb.tf",
        "lb.tf",
        "variables.tf",
        "outputs.tf",
        "terraform.tfvars",
        "terraform.tfvars.example",
    ]
    for filename in required_files:
        path = TF_DIR / filename
        assert path.exists(), f"Missing required terraform file: {filename}"


def test_variables_configuration():
    """Verify variables.tf defines access_mode, Argolis identities, and VPC networking."""
    variables_content = (TF_DIR / "variables.tf").read_text()
    assert 'variable "access_mode"' in variables_content
    assert '"proxy"' in variables_content
    assert '"internal_lb"' in variables_content
    assert 'variable "argolis_tenant_domain"' in variables_content
    assert 'variable "argolis_allowed_invokers"' in variables_content
    assert 'variable "vpc_network"' in variables_content
    assert 'variable "vpc_subnet"' in variables_content
    assert 'variable "create_proxy_only_subnet"' in variables_content


def test_cloud_run_ingress_and_iam():
    """Verify Cloud Run v2 enforces --no-allow-unauthenticated and dynamic ingress."""
    cloud_run_content = (TF_DIR / "cloud_run.tf").read_text()
    assert "ingress = local.cloud_run_ingress" in cloud_run_content
    assert "resource \"google_cloud_run_v2_service_iam_member\" \"argolis_invokers\"" in cloud_run_content
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


def test_argolis_access_script():
    """Verify scripts/argolis_access.sh is executable and provides help/proxy/token."""
    script_path = SCRIPTS_DIR / "argolis_access.sh"
    assert script_path.exists(), "scripts/argolis_access.sh does not exist"
    assert os.access(script_path, os.X_OK), "scripts/argolis_access.sh must be executable"

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
    assert "Usage: ./scripts/argolis_access.sh" in result.stdout
    assert "proxy" in result.stdout
    assert "token" in result.stdout
    assert "curl" in result.stdout
    assert "status" in result.stdout


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
