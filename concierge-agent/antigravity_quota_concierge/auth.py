"""End-user identity resolution and Agent-to-Portal authentication helpers.

Handles:
1. Extracting the employee's verified email address from Gemini Enterprise's
   delegated OAuth/session `ToolContext` (including JWT `id_token` claims,
   `auth_response`, and session `state`), with fallback to an explicit email or
   `DEFAULT_DEMO_USER_EMAIL` in local/demo mode.
2. Constructing IAM-authenticated HTTP headers (`Authorization: Bearer <OIDC>`,
   `X-User-Email`, and `X-Impersonate-User`) so the Vertex AI Agent Engine
   service account can securely query and submit requests to the
   `antigravity-quota-portal` Cloud Run service on behalf of the employee.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

from antigravity_quota_concierge._adk_compat import ToolContext

logger = logging.getLogger(__name__)

DEFAULT_DEMO_USER_EMAIL = os.environ.get("DEFAULT_DEMO_USER_EMAIL", "").strip().lower()
DEFAULT_CONCIERGE_SA_EMAIL = "antigravity-concierge@example.iam.gserviceaccount.com"


def decode_jwt_email_claim(token: str) -> str | None:
    """Extract the `email` (or `upn` / `preferred_username`) claim from a JWT token."""
    if not token or not isinstance(token, str):
        return None

    clean_token = token.strip()
    if clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()

    # 1. Try PyJWT if available
    try:
        import jwt  # type: ignore[import-untyped]

        claims = jwt.decode(clean_token, options={"verify_signature": False})
        if isinstance(claims, dict):
            for key in ("email", "upn", "preferred_username"):
                val = claims.get(key)
                if isinstance(val, str) and "@" in val:
                    return val.strip().lower()
    except Exception:
        pass

    # 2. Standard-library base64url JWT payload decode fallback
    parts = clean_token.split(".")
    if len(parts) < 2:
        return None
    try:
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        decoded_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        claims = json.loads(decoded_bytes.decode("utf-8"))
        if isinstance(claims, dict):
            for key in ("email", "upn", "preferred_username"):
                val = claims.get(key)
                if isinstance(val, str) and "@" in val:
                    return val.strip().lower()
    except Exception:
        return None

    return None


def resolve_employee_email(
    tool_context: ToolContext | None = None,
    explicit_email: str | None = None,
) -> str:
    """Resolve the caller's email from Gemini Enterprise authenticated session or explicit input.

    Zero-Trust / Authenticated Identity Resolution:
    1. Gemini Enterprise ToolContext / Session principal:
       a. `tool_context.user_id` (Google Workspace corporate email passed by Gemini Enterprise).
       b. `tool_context.session.user_id`
       c. `tool_context.get_invocation_context().user_id`
       d. `tool_context.auth_response` (OAuth JWT `id_token` claims / `email`)
       e. `tool_context.state` (`resolved_user_email`, `user_email`, `email`)
    2. Explicit `explicit_email` (e.g., when the employee provides their email in chat:
       "My email is alex.morgan@example.com" or passed as a tool argument).
    3. `DEFAULT_DEMO_USER_EMAIL` environment variable fallback (only if explicitly set in env).
    4. Returns empty string `""` if no identity is found, prompting the agent to ask the user.
    """
    context_email: str | None = None

    if tool_context is not None:
        # 1a. Check tool_context.user_id (Gemini Enterprise authenticated caller)
        uid = getattr(tool_context, "user_id", None)
        if isinstance(uid, str) and "@" in uid:
            context_email = uid.strip().lower()

        # 1b. Check session.user_id
        if not context_email:
            session = getattr(tool_context, "session", None)
            if session is not None:
                s_uid = getattr(session, "user_id", None)
                if isinstance(s_uid, str) and "@" in s_uid:
                    context_email = s_uid.strip().lower()

        # 1c. Check invocation context directly
        if not context_email:
            inv_fn = getattr(tool_context, "get_invocation_context", None)
            if callable(inv_fn):
                try:
                    inv_ctx = inv_fn()
                    i_uid = getattr(inv_ctx, "user_id", None)
                    if isinstance(i_uid, str) and "@" in i_uid:
                        context_email = i_uid.strip().lower()
                except Exception:
                    pass

        # 1d. Check auth_response (GeminiEnterpriseDelegatedAuthProvider / OAuth)
        if not context_email:
            auth_resp = getattr(tool_context, "auth_response", None)
            if isinstance(auth_resp, dict):
                for key in ("email", "user_email", "upn"):
                    val = auth_resp.get(key)
                    if isinstance(val, str) and "@" in val:
                        context_email = val.strip().lower()
                        break

                if not context_email:
                    for token_key in ("id_token", "access_token", "token", "jwt"):
                        token_val = auth_resp.get(token_key)
                        if isinstance(token_val, str):
                            claim_email = decode_jwt_email_claim(token_val)
                            if claim_email:
                                context_email = claim_email
                                break

        # 1e. Check session state dictionary
        state = getattr(tool_context, "state", None)
        if not context_email and isinstance(state, dict):
            for key in ("resolved_user_email", "user_email", "email", "caller_email", "user:email"):
                val = state.get(key)
                if isinstance(val, str) and "@" in val:
                    context_email = val.strip().lower()
                    break

            if not context_email:
                user_info = state.get("user_info") or state.get("user")
                if isinstance(user_info, dict):
                    val = user_info.get("email") or user_info.get("user_email")
                    if isinstance(val, str) and "@" in val:
                        context_email = val.strip().lower()

            if not context_email:
                for token_key in ("id_token", "access_token", "oauth_token"):
                    token_val = state.get(token_key)
                    if isinstance(token_val, str):
                        claim_email = decode_jwt_email_claim(token_val)
                        if claim_email:
                            context_email = claim_email
                            break

    if context_email:
        if tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
            tool_context.state["user:email"] = context_email
            tool_context.state["resolved_user_email"] = context_email
        return context_email

    # 2. Allow explicit_email when no authenticated session principal is bound
    if explicit_email and isinstance(explicit_email, str) and "@" in explicit_email:
        resolved = explicit_email.strip().lower()
        if tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
            tool_context.state["user:email"] = resolved
            tool_context.state["resolved_user_email"] = resolved
        return resolved

    # 3. Environment variable fallback (only if explicitly set in environment)
    env_default = os.environ.get("DEFAULT_DEMO_USER_EMAIL", "").strip().lower()
    if env_default:
        if tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
            tool_context.state["user:email"] = env_default
            tool_context.state["resolved_user_email"] = env_default
        return env_default

    return ""


def resolve_portal_oidc_audience(
    portal_base_url: str,
    force_direct_audience: bool = False,
) -> str:
    """Resolve target audience for Google-signed OIDC ID tokens.

    Resolution precedence:
    1. `force_direct_audience=True`: Explicitly uses `portal_base_url` as the OIDC
       audience (used when falling back from GCLB+IAP to the direct Cloud Run `.run.app`
       service URL after switching back to `proxy` mode).
    2. `PORTAL_IAP_CLIENT_ID`: Required when the portal is fronted by an External HTTPS
       Load Balancer with Identity-Aware Proxy (IAP) enabled. Audience must match the
       IAP OAuth Client ID (e.g. `<project-num>-<hash>.apps.googleusercontent.com`).
    3. `PORTAL_OIDC_AUDIENCE`: Explicit override audience (e.g. custom Cloud Run service URL
       when accessed via an enterprise gateway or internal proxy).
    4. `portal_base_url`: Default audience matching the direct Cloud Run service HTTPS URL.
    """
    clean_base = portal_base_url.rstrip("/")
    if force_direct_audience:
        return clean_base

    iap_client_id = os.environ.get("PORTAL_IAP_CLIENT_ID", "").strip()
    if iap_client_id:
        return iap_client_id

    custom_audience = os.environ.get("PORTAL_OIDC_AUDIENCE", "").strip()
    if custom_audience:
        return custom_audience

    return clean_base


def fetch_cloud_run_id_token(target_audience: str) -> str | None:
    """Fetch a Google-signed OIDC ID token for invoking a private Cloud Run or IAP service."""
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import id_token

        return id_token.fetch_id_token(GoogleAuthRequest(), target_audience)
    except Exception as exc:
        logger.debug(f"Could not fetch OIDC token for audience '{target_audience}': {exc}")
        return None


def build_portal_auth_headers(
    target_user_email: str,
    portal_base_url: str | None = None,
    force_direct_audience: bool = False,
) -> dict[str, str]:
    """Build authentication and user-impersonation headers for Portal API requests.

    Supports:
    1. Direct Cloud Run IAM (`roles/run.invoker`) with base_url as token audience.
    2. External Load Balancer with Identity-Aware Proxy (IAP) using `PORTAL_IAP_CLIENT_ID`.
    3. Proxy/Gateway topologies (Enterprise reverse proxies, Internal LB proxies) using
       `PORTAL_OIDC_AUDIENCE` and optional `PORTAL_EXTRA_HEADERS_JSON`.
    4. Automatic dual-endpoint fallback (`force_direct_audience=True`) when switching
       between GCLB+IAP and `proxy` mode.
    """
    clean_user = target_user_email.strip().lower()
    service_account_email = os.environ.get(
        "CONCIERGE_SERVICE_ACCOUNT_EMAIL",
        DEFAULT_CONCIERGE_SA_EMAIL,
    ).strip().lower()

    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-User-Email": service_account_email,
        "X-Impersonate-User": clean_user,
    }

    # Inject any custom proxy headers (e.g. for enterprise reverse proxy or custom gateways)
    extra_headers_raw = os.environ.get("PORTAL_EXTRA_HEADERS_JSON", "").strip()
    if extra_headers_raw:
        try:
            extra_headers = json.loads(extra_headers_raw)
            if isinstance(extra_headers, dict):
                for k, v in extra_headers.items():
                    if isinstance(k, str) and isinstance(v, str):
                        headers[k] = v
        except Exception as exc:
            logger.debug(f"Failed to parse PORTAL_EXTRA_HEADERS_JSON: {exc}")

    base_url = (portal_base_url or os.environ.get("PORTAL_API_BASE_URL", "http://localhost:8080")).rstrip("/")
    use_oidc_env = os.environ.get("PORTAL_USE_OIDC_TOKEN", "").strip().lower()
    has_explicit_audience = bool(os.environ.get("PORTAL_IAP_CLIENT_ID") or os.environ.get("PORTAL_OIDC_AUDIENCE"))
    should_attach_oidc = use_oidc_env == "true" or has_explicit_audience or force_direct_audience or (
        use_oidc_env != "false"
        and base_url.startswith("https://")
        and "localhost" not in base_url
        and "127.0.0.1" not in base_url
    )

    if should_attach_oidc:
        target_audience = resolve_portal_oidc_audience(
            base_url,
            force_direct_audience=force_direct_audience,
        )
        oidc_token = fetch_cloud_run_id_token(target_audience)
        if oidc_token:
            headers["Authorization"] = f"Bearer {oidc_token}"
            if os.environ.get("PORTAL_USE_PROXY_AUTH_HEADER", "").strip().lower() == "true":
                headers["Proxy-Authorization"] = f"Bearer {oidc_token}"

    return headers
