#!/usr/bin/env python3
"""Deploy Antigravity Quota Concierge (`AdkApp`) to Vertex AI Agent Engine.

Wraps `root_agent` in an `AdkApp` subclass with explicit generator streaming
(`stream_query`) for Gemini Enterprise compatibility, deploys it to Vertex AI
Agent Engine (`ReasoningEngine.create`), and writes `deployment_metadata.json`
for one-command registration with `agents-cli publish gemini-enterprise`.

Usage (from inside `concierge-agent/`):
    # Dry-run verification (no GCP calls):
    python3 -m antigravity_quota_concierge.deploy_agent_engine --dry-run

    # Deploy to Vertex AI Agent Engine:
    python3 -m antigravity_quota_concierge.deploy_agent_engine \
        --project-id "$PROJECT_ID" \
        --location "us-central1" \
        --staging-bucket "gs://$PROJECT_ID-agent-staging" \
        --portal-api-url "https://antigravity-quota-portal-xyz.a.run.app"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from antigravity_quota_concierge.agent import DEFAULT_CONCIERGE_MODEL, root_agent

AGENT_DISPLAY_NAME = "Antigravity Quota Concierge"
AGENT_DESCRIPTION = (
    "Internal Gemini Enterprise Multi-Agent Concierge that checks why an employee's "
    "Antigravity access is paused, coaches on model token efficiency, and submits "
    "quota increase requests via the Antigravity Quota & Usage Management Portal."
)

AGENT_ENGINE_REQUIREMENTS = [
    "google-cloud-aiplatform[agent_engines,adk]",
    "httpx>=0.27.0",
]


def create_adk_app(
    portal_api_url: str | None = None,
    concierge_sa_email: str | None = None,
    model_name: str | None = None,
    env_vars: dict[str, str] | None = None,
) -> Any:
    """Create the `AdkApp` wrapper for Vertex AI Agent Engine deployment."""
    if portal_api_url:
        os.environ["PORTAL_API_BASE_URL"] = portal_api_url
    if concierge_sa_email:
        os.environ["CONCIERGE_SERVICE_ACCOUNT_EMAIL"] = concierge_sa_email
    if model_name:
        os.environ["CONCIERGE_MODEL"] = model_name

    try:
        from vertexai.preview.reasoning_engines import AdkApp  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "vertexai.preview.reasoning_engines.AdkApp is required for Agent Engine deployment. "
            'Install with: pip install "google-cloud-aiplatform[agent_engines,adk]>=1.129.0"'
        ) from exc

    class AntigravityConciergeAdkApp(AdkApp):  # type: ignore[misc]
        """AdkApp wrapper with explicit generator `stream_query` for Gemini Enterprise."""

        def stream_query(self, *args: Any, **kwargs: Any):
            # Must use `yield from` so Vertex AI Reasoning Engine registers it as a streaming endpoint
            yield from super().stream_query(*args, **kwargs)

        def query(self, *args: Any, **kwargs: Any) -> Any:
            # AdkApp does not implement query() natively; accumulate stream_query for unary compatibility
            response_chunks = []
            for chunk in self.stream_query(*args, **kwargs):
                response_chunks.append(str(chunk))
            return "".join(response_chunks)

    return AntigravityConciergeAdkApp(
        agent=root_agent,
        env_vars=env_vars,
    )


def deploy_to_agent_engine(
    project_id: str,
    location: str,
    staging_bucket: str,
    portal_api_url: str,
    concierge_sa_email: str = "",
    iap_client_id: str = "",
    oidc_audience: str = "",
    fallback_cloud_run_url: str = "",
    extra_headers_json: str = "",
    use_proxy_auth: bool = False,
    display_name: str = AGENT_DISPLAY_NAME,
    description: str = AGENT_DESCRIPTION,
    metadata_output_path: str = "deployment_metadata.json",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Deploy `AntigravityConciergeAdkApp` to Vertex AI Agent Engine and write metadata."""
    env_vars = {
        "PORTAL_API_BASE_URL": portal_api_url.rstrip("/"),
        "CONCIERGE_MODEL": os.environ.get("CONCIERGE_MODEL", DEFAULT_CONCIERGE_MODEL),
        "PORTAL_USE_OIDC_TOKEN": "true",
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "GOOGLE_CLOUD_LOCATION": "global",
    }
    if concierge_sa_email:
        env_vars["CONCIERGE_SERVICE_ACCOUNT_EMAIL"] = concierge_sa_email
    if iap_client_id:
        env_vars["PORTAL_IAP_CLIENT_ID"] = iap_client_id
    elif os.environ.get("PORTAL_IAP_CLIENT_ID"):
        env_vars["PORTAL_IAP_CLIENT_ID"] = os.environ["PORTAL_IAP_CLIENT_ID"]

    if oidc_audience:
        env_vars["PORTAL_OIDC_AUDIENCE"] = oidc_audience
    elif os.environ.get("PORTAL_OIDC_AUDIENCE"):
        env_vars["PORTAL_OIDC_AUDIENCE"] = os.environ["PORTAL_OIDC_AUDIENCE"]

    if fallback_cloud_run_url:
        env_vars["PORTAL_FALLBACK_CLOUD_RUN_URL"] = fallback_cloud_run_url.rstrip("/")
    elif os.environ.get("PORTAL_FALLBACK_CLOUD_RUN_URL"):
        env_vars["PORTAL_FALLBACK_CLOUD_RUN_URL"] = os.environ["PORTAL_FALLBACK_CLOUD_RUN_URL"].rstrip("/")

    if extra_headers_json:
        env_vars["PORTAL_EXTRA_HEADERS_JSON"] = extra_headers_json
    elif os.environ.get("PORTAL_EXTRA_HEADERS_JSON"):
        env_vars["PORTAL_EXTRA_HEADERS_JSON"] = os.environ["PORTAL_EXTRA_HEADERS_JSON"]

    if use_proxy_auth or os.environ.get("PORTAL_USE_PROXY_AUTH_HEADER", "").strip().lower() == "true":
        env_vars["PORTAL_USE_PROXY_AUTH_HEADER"] = "true"

    concierge_dir = Path(__file__).resolve().parent.parent

    # Purge local __pycache__ directories so bytecode files do not leak into container tarball
    for pycache in concierge_dir.glob("**/__pycache__"):
        if pycache.is_dir():
            shutil.rmtree(pycache, ignore_errors=True)

    # Change working directory so relative package paths are archived cleanly in dependencies.tar.gz
    # (avoiding host-specific absolute paths inside the container /code root)
    os.chdir(concierge_dir)
    extra_packages = ["antigravity_quota_concierge"]

    deployment_plan = {
        "project_id": project_id,
        "location": location,
        "staging_bucket": staging_bucket,
        "display_name": display_name,
        "description": description,
        "root_agent_name": root_agent.name,
        "model": env_vars["CONCIERGE_MODEL"],
        "sub_agents": [sa.name for sa in getattr(root_agent, "sub_agents", [])],
        "requirements": AGENT_ENGINE_REQUIREMENTS,
        "env_vars": env_vars,
        "extra_packages": extra_packages,
    }

    if dry_run:
        return {"status": "dry_run", "deployment_plan": deployment_plan}

    import vertexai  # type: ignore[import-untyped]
    from vertexai.preview.reasoning_engines import ReasoningEngine  # type: ignore[import-untyped]

    vertexai.init(
        project=project_id,
        location=location,
        staging_bucket=staging_bucket,
    )

    adk_app = create_adk_app(
        portal_api_url=portal_api_url,
        concierge_sa_email=concierge_sa_email,
        model_name=env_vars["CONCIERGE_MODEL"],
        env_vars=env_vars,
    )

    remote_agent = ReasoningEngine.create(
        reasoning_engine=adk_app,
        requirements=AGENT_ENGINE_REQUIREMENTS,
        extra_packages=extra_packages,
        display_name=display_name,
        description=description,
    )

    resource_name = str(getattr(remote_agent, "resource_name", ""))
    try:
        import subprocess
        import requests
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()
        url = f"https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}?updateMask=spec.agent_framework"
        requests.patch(
            url,
            headers={"Authorization": f"Bearer {token}", "x-goog-user-project": project_id},
            json={"spec": {"agent_framework": "google-adk"}},
            timeout=15,
        )
    except Exception:
        pass

    metadata = {
        "remote_agent_runtime_id": resource_name,
        "deployment_target": "agent_runtime",
        "is_a2a": False,
        "project_id": project_id,
        "location": location,
        "display_name": display_name,
        "description": description,
        "tool_description": (
            "Use this tool when the user asks about Antigravity access, weekly quota limits, "
            "why their Antigravity or code assistance is paused or blocked, how to unpause or "
            "get more quota, how to submit or check a quota increase request, model token "
            "efficiency or spend coaching, or weekly quota reset countdowns."
        ),
        "portal_api_url": portal_api_url,
    }

    if metadata_output_path:
        Path(metadata_output_path).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    return {
        "status": "deployed",
        "resource_name": resource_name,
        "metadata_file": metadata_output_path,
        "metadata": metadata,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deploy Antigravity Quota Concierge ADK Agent to Vertex AI Agent Engine."
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID", "local-project"),
        help="GCP Project ID hosting Vertex AI Agent Engine and Gemini Enterprise.",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get("REGION", "us-central1"),
        help="GCP region for Vertex AI Agent Engine (default: us-central1).",
    )
    parser.add_argument(
        "--staging-bucket",
        default=os.environ.get("AGENT_ENGINE_STAGING_BUCKET", ""),
        help="GCS bucket URI (gs://...) for staging Agent Engine artifacts.",
    )
    parser.add_argument(
        "--portal-api-url",
        default=os.environ.get("PORTAL_API_BASE_URL", "https://antigravity-quota-portal-example.a.run.app"),
        help="Base URL of the deployed Antigravity Quota Portal Cloud Run service.",
    )
    parser.add_argument(
        "--concierge-sa-email",
        default=os.environ.get("CONCIERGE_SERVICE_ACCOUNT_EMAIL", ""),
        help="Service account email used by the Concierge to authenticate to the Portal.",
    )
    parser.add_argument(
        "--iap-client-id",
        default=os.environ.get("PORTAL_IAP_CLIENT_ID", ""),
        help="OAuth Client ID for Cloud IAP (e.g. 12345-abc.apps.googleusercontent.com) when behind an IAP Load Balancer.",
    )
    parser.add_argument(
        "--oidc-audience",
        default=os.environ.get("PORTAL_OIDC_AUDIENCE", ""),
        help="Custom OIDC audience override when accessing the portal via an enterprise or internal proxy.",
    )
    parser.add_argument(
        "--fallback-cloud-run-url",
        default=os.environ.get("PORTAL_FALLBACK_CLOUD_RUN_URL", ""),
        help="Optional fallback direct Cloud Run URL (.run.app) for seamless switching between GCLB+IAP and proxy mode.",
    )
    parser.add_argument(
        "--extra-headers-json",
        default=os.environ.get("PORTAL_EXTRA_HEADERS_JSON", ""),
        help="JSON string of additional HTTP headers to attach to Portal requests (e.g. for reverse proxies).",
    )
    parser.add_argument(
        "--use-proxy-auth",
        action="store_true",
        default=os.environ.get("PORTAL_USE_PROXY_AUTH_HEADER", "").strip().lower() == "true",
        help="Attach the OIDC token in the `Proxy-Authorization` header in addition to `Authorization`.",
    )
    parser.add_argument(
        "--display-name",
        default=AGENT_DISPLAY_NAME,
        help="Display name in Vertex AI Agent Engine and Gemini Enterprise.",
    )
    parser.add_argument(
        "--metadata-file",
        default="deployment_metadata.json",
        help="Output path for deployment_metadata.json (used by `agents-cli publish gemini-enterprise`).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate agent configuration and print the deployment plan without calling Vertex AI.",
    )

    args = parser.parse_args(argv)
    if not args.dry_run and not args.staging_bucket:
        args.staging_bucket = f"gs://{args.project_id}-agent-staging"

    result = deploy_to_agent_engine(
        project_id=args.project_id,
        location=args.location,
        staging_bucket=args.staging_bucket,
        portal_api_url=args.portal_api_url,
        concierge_sa_email=args.concierge_sa_email,
        iap_client_id=args.iap_client_id,
        oidc_audience=args.oidc_audience,
        fallback_cloud_run_url=args.fallback_cloud_run_url,
        extra_headers_json=args.extra_headers_json,
        use_proxy_auth=args.use_proxy_auth,
        display_name=args.display_name,
        metadata_output_path=args.metadata_file,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
