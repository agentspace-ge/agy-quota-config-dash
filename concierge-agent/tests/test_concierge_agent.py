"""Unit and integration tests for the Antigravity Quota Concierge ADK Multi-Agent system."""

from __future__ import annotations

import base64
import json
import unittest
from typing import Any

from antigravity_quota_concierge import (
    DEFAULT_CONCIERGE_MODEL,
    quota_request_agent,
    root_agent,
)
from antigravity_quota_concierge._adk_compat import ToolContext
from antigravity_quota_concierge.auth import (
    build_portal_auth_headers,
    decode_jwt_email_claim,
    resolve_employee_email,
    resolve_portal_oidc_audience,
)
from antigravity_quota_concierge.deploy_agent_engine import deploy_to_agent_engine
from antigravity_quota_concierge.tools import (
    cancel_pending_quota_request,
    get_model_efficiency_insights,
    get_my_quota_requests,
    get_my_quota_status,
    get_quota_request_options,
    normalize_duration,
    normalize_reason_category,
    set_custom_http_requester,
    submit_quota_increase_request,
)


def _make_fake_jwt(claims: dict[str, Any]) -> str:
    """Create an unsigned JWT string for testing OAuth `id_token` claim extraction."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{header}.{payload}.signature"


class FakePortalBackend:
    """In-memory mock of the Antigravity Quota Portal REST API (`/api/auth/me` & `/api/quota-requests`)."""

    def __init__(self) -> None:
        self.last_headers: dict[str, str] = {}
        self.users: dict[str, dict[str, Any]] = {
            "alex.morgan@example.com": {
                "email": "alex.morgan@example.com",
                "group_id": "business-users",
                "status": "AUTO_DISABLED",
                "is_exempt": False,
                "has_custom_quota": True,
                "custom_quota_usd": 6.00,
                "current_week": {
                    "week_id": "2026-W41",
                    "gross_spend_usd": 6.04,
                    "quota_credits_usd": 6.00,
                    "overage_buffer_usd": 0.00,
                    "remaining_credit_usd": 0.00,
                    "credit_utilization_percentage": 100.67,
                    "tokens_by_model": {"gemini-3-pro": 2200000, "gemini-3.5-flash": 750000},
                    "spend_by_model": {"gemini-3-pro": 5.60, "gemini-3.5-flash": 0.44},
                },
            },
            "charlie.davis@example.com": {
                "email": "charlie.davis@example.com",
                "group_id": "business-users",
                "status": "AUTO_DISABLED",
                "is_exempt": False,
                "has_custom_quota": False,
                "current_week": {
                    "week_id": "2026-W41",
                    "gross_spend_usd": 13.40,
                    "quota_credits_usd": 10.00,
                    "overage_buffer_usd": 2.00,
                    "remaining_credit_usd": 0.00,
                    "credit_utilization_percentage": 134.0,
                    "tokens_by_model": {"gemini-3-pro": 5800000},
                    "spend_by_model": {"gemini-3-pro": 11.50},
                },
            },
            "alice.chen@example.com": {
                "email": "alice.chen@example.com",
                "group_id": "developers",
                "status": "ACTIVE",
                "is_exempt": False,
                "has_custom_quota": False,
                "current_week": {
                    "week_id": "2026-W41",
                    "gross_spend_usd": 4.20,
                    "quota_credits_usd": 10.00,
                    "overage_buffer_usd": 2.00,
                    "remaining_credit_usd": 5.80,
                    "credit_utilization_percentage": 42.0,
                    "tokens_by_model": {"gemini-3-pro": 500000, "gemini-3.5-flash": 2000000},
                    "spend_by_model": {"gemini-3-pro": 1.20, "gemini-3.5-flash": 3.00},
                },
            },
        }
        self.pending_requests: dict[str, dict[str, Any]] = {}
        self._req_counter = 0
        self.cooldown_by_user: dict[str, dict[str, Any]] = {}

    def handle_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        self.last_headers = dict(headers)
        effective_email = (headers.get("X-Impersonate-User") or headers.get("X-User-Email") or "").strip().lower()

        if method == "GET" and path == "/api/auth/me":
            user = self.users.get(effective_email)
            if not user:
                return 404, {"detail": f"User {effective_email} not found"}
            active_req = next(
                (
                    r
                    for r in self.pending_requests.values()
                    if r["user_email"] == effective_email and r["status"] == "PENDING"
                ),
                None,
            )
            cd = self.cooldown_by_user.get(effective_email, {})
            group_display = "Developers" if user["group_id"] == "developers" else "Business Users"
            return 200, {
                "email": effective_email,
                "caller_email": headers.get("X-User-Email"),
                "is_admin": False,
                "is_impersonating": True,
                "user": user,
                "group": {"group_id": user["group_id"], "display_name": group_display},
                "credit_pool": {"next_reset_utc": "2026-10-19T00:00:00Z"},
                "active_request": active_req,
                "in_cooldown": bool(cd.get("in_cooldown", False)),
                "cooldown_until": cd.get("cooldown_until"),
                "admin_note": cd.get("admin_note"),
                "warning_threshold_reached": user["current_week"]["credit_utilization_percentage"] >= 80.0,
            }

        if method == "GET" and path.startswith("/api/quota-requests"):
            reqs = [r for r in self.pending_requests.values() if r["user_email"] == effective_email]
            return 200, reqs

        if method == "POST" and path == "/api/quota-requests":
            for req in self.pending_requests.values():
                if req["user_email"] == effective_email and req["status"] == "PENDING":
                    return 409, {"detail": "A quota increase request is already pending review for your account."}
            self._req_counter += 1
            req_id = f"req-demo-{self._req_counter:04d}"
            created = {
                "request_id": req_id,
                "user_email": effective_email,
                "requested_quota_usd": json_body["requested_quota_usd"],
                "reason_category": json_body["reason_category"],
                "justification": json_body["justification"],
                "duration_needed": json_body["duration_needed"],
                "status": "PENDING",
            }
            self.pending_requests[req_id] = created
            return 201, created

        if method == "DELETE" and path.startswith("/api/quota-requests/"):
            req_id = path.rsplit("/", 1)[-1]
            req = self.pending_requests.get(req_id)
            if not req or req["user_email"] != effective_email or req["status"] != "PENDING":
                return 400, {"detail": "Cannot cancel request"}
            req["status"] = "CANCELLED"
            return 200, req

        return 404, {"detail": f"Unhandled route {method} {path}"}


class TestAntigravityQuotaConcierge(unittest.TestCase):
    """Test suite for Antigravity Quota Concierge multi-agent topology, auth, coaching, and request tools."""

    def setUp(self) -> None:
        self.backend = FakePortalBackend()
        set_custom_http_requester(self.backend.handle_request)

    def tearDown(self) -> None:
        set_custom_http_requester(None)

    def test_multi_agent_topology_and_gemini_3_5_flash_model(self) -> None:
        """Verify Root Concierge and Quota Request Sub-Agent use gemini-3.5-flash and wire all 6 tools."""
        self.assertEqual(DEFAULT_CONCIERGE_MODEL, "gemini-3.5-flash")
        self.assertEqual(root_agent.name, "antigravity_quota_concierge")
        self.assertEqual(root_agent.model, "gemini-3.5-flash")
        self.assertEqual(quota_request_agent.name, "quota_request_agent")
        self.assertEqual(quota_request_agent.model, "gemini-3.5-flash")

        # Verify sub-agent delegation wiring
        self.assertIn(quota_request_agent, root_agent.sub_agents)

        # Verify 2 diagnostic/coaching tools on Root Agent and 4 request lifecycle tools on Sub-Agent
        self.assertIn(get_my_quota_status, root_agent.tools)
        self.assertIn(get_model_efficiency_insights, root_agent.tools)
        self.assertIn(get_quota_request_options, quota_request_agent.tools)
        self.assertIn(get_my_quota_requests, quota_request_agent.tools)
        self.assertIn(submit_quota_increase_request, quota_request_agent.tools)
        self.assertIn(cancel_pending_quota_request, quota_request_agent.tools)

    def test_quota_request_agent_task_mode_and_schema(self) -> None:
        from antigravity_quota_concierge import quota_request_agent
        from antigravity_quota_concierge.schemas import QuotaRequestTaskOutput

        self.assertEqual(quota_request_agent.mode, "task")
        self.assertEqual(quota_request_agent.output_schema, QuotaRequestTaskOutput)

    def test_identity_resolution_from_oauth_jwt_and_state(self) -> None:
        """Verify employee email is extracted from Gemini Enterprise OAuth JWT or session state."""
        jwt_token = _make_fake_jwt({"email": "Alex.Morgan@example.com", "sub": "12345"})
        self.assertEqual(decode_jwt_email_claim(jwt_token), "alex.morgan@example.com")

        ctx_jwt = ToolContext(auth_response={"id_token": f"Bearer {jwt_token}"})
        self.assertEqual(resolve_employee_email(ctx_jwt), "alex.morgan@example.com")
        self.assertEqual(ctx_jwt.state["resolved_user_email"], "alex.morgan@example.com")

        ctx_state = ToolContext(state={"user_email": "Alice.Chen@example.com"})
        self.assertEqual(resolve_employee_email(ctx_state), "alice.chen@example.com")

        # Verify Confused Deputy / IDOR protection: authenticated ToolContext always wins over explicit_email
        self.assertEqual(
            resolve_employee_email(ctx_jwt, explicit_email="vp-engineering@example.com"),
            "alex.morgan@example.com",
        )
        self.assertEqual(
            resolve_employee_email(ctx_state, explicit_email="boss@example.com"),
            "alice.chen@example.com",
        )
        # Explicit email is only used when ToolContext has no authenticated identity
        self.assertEqual(
            resolve_employee_email(None, explicit_email="Charlie.Davis@example.com"),
            "charlie.davis@example.com",
        )

        headers = build_portal_auth_headers("alex.morgan@example.com", "http://localhost:8080")
        self.assertEqual(headers["X-Impersonate-User"], "alex.morgan@example.com")
        self.assertIn("X-User-Email", headers)

    def test_paused_diagnostic_exact_reply_and_reset_countdown(self) -> None:
        """Verify the exact $6.04 / $6.00 diagnostic reply, reset countdown, and group tier metadata."""
        jwt_token = _make_fake_jwt({"email": "alex.morgan@example.com"})
        ctx = ToolContext(auth_response={"id_token": jwt_token})

        status_res = get_my_quota_status(tool_context=ctx)
        self.assertEqual(status_res["status"], "success")
        self.assertEqual(status_res["user_email"], "alex.morgan@example.com")
        self.assertEqual(status_res["account_status"], "AUTO_DISABLED")
        self.assertTrue(status_res["is_paused"])
        self.assertEqual(status_res["weekly_usage_usd"], 6.04)
        self.assertEqual(status_res["weekly_limit_usd"], 6.00)
        self.assertTrue(status_res["is_default_business_tier"])
        self.assertIn("reset_countdown", status_res)

        expected_reply = (
            "Your Antigravity access is currently paused because your weekly usage reached "
            "$6.04, which exceeds your $6.00 limit. Would you like me to submit an increase "
            "request to your manager or administrator?"
        )
        self.assertEqual(status_res["suggested_reply"], expected_reply)
        self.assertEqual(self.backend.last_headers["X-Impersonate-User"], "alex.morgan@example.com")

    def test_model_efficiency_insights_pro_vs_flash_coaching(self) -> None:
        """Verify `get_model_efficiency_insights` computes Pro vs Flash spend split and FinOps coaching."""
        ctx = ToolContext(state={"user_email": "alex.morgan@example.com"})
        insights = get_model_efficiency_insights(tool_context=ctx)

        self.assertEqual(insights["status"], "success")
        self.assertEqual(insights["frontier_spend_usd"], 5.60)
        self.assertEqual(insights["lightweight_spend_usd"], 0.44)
        self.assertGreater(insights["frontier_percentage"], 90.0)
        self.assertIn("gemini-3.5-flash", insights["coaching_recommendation"])
        self.assertIn("3–4x longer", insights["coaching_recommendation"])

    def test_subagent_preset_options_and_single_message_submission(self) -> None:
        """Verify sub-agent presents the 3 numbered preset options, role upgrade advice, and submits."""
        ctx = ToolContext(state={"user_email": "alex.morgan@example.com"})

        # Step 1: Root agent runs diagnostic
        get_my_quota_status(tool_context=ctx)

        # Step 2: Employee says "Yes" -> Sub-agent fetches options
        options_res = get_quota_request_options(tool_context=ctx)
        self.assertEqual(options_res["status"], "success")
        self.assertEqual(options_res["current_quota_usd"], 6.00)
        self.assertIsNotNone(options_res["role_upgrade_advice"])
        presets = options_res["preset_options"]
        self.assertEqual(len(presets), 3)
        # Option 1: $6 + $15 = $21 (Temporary)
        self.assertEqual(presets[0]["requested_quota_usd"], 21.00)
        self.assertEqual(presets[0]["duration_needed"], "TEMPORARY_WEEKLY")
        # Option 2 (Recommended): $6 + $25 = $31 (Temporary)
        self.assertEqual(presets[1]["requested_quota_usd"], 31.00)
        self.assertTrue(presets[1]["recommended"])
        # Option 3: $6 + $50 = $56 (Permanent)
        self.assertEqual(presets[2]["requested_quota_usd"], 56.00)
        self.assertEqual(presets[2]["duration_needed"], "PERMANENT")

        # Step 3: Employee replies "Option 2 for a sprint deadline on checkout API"
        submit_res = submit_quota_increase_request(
            requested_quota_usd=2,  # Option 2
            reason_category="sprint deadline",
            justification="Finishing Q4 checkout service sprint milestone",
            tool_context=ctx,
        )
        self.assertEqual(submit_res["status"], "submitted")
        self.assertEqual(submit_res["previous_quota_usd"], 6.00)
        self.assertEqual(submit_res["requested_quota_usd"], 31.00)
        self.assertEqual(submit_res["duration_needed"], "TEMPORARY_WEEKLY")
        self.assertEqual(submit_res["reason_category"], "SPRINT_DEADLINE")
        req_id = submit_res["request_id"]
        self.assertTrue(req_id.startswith("req-demo-"))

        # Step 4: Employee asks "What is the status of my quota request?"
        history_res = get_my_quota_requests(tool_context=ctx)
        self.assertEqual(history_res["status"], "success")
        self.assertEqual(history_res["pending_count"], 1)
        self.assertEqual(history_res["active_pending_request"]["request_id"], req_id)

        # Step 5: Duplicate submission while pending returns 409 conflict_already_pending
        dup_res = submit_quota_increase_request(
            requested_quota_usd=50.0,
            reason_category="INCIDENT",
            justification="Duplicate test",
            tool_context=ctx,
        )
        self.assertEqual(dup_res["status"], "conflict_already_pending")
        self.assertEqual(dup_res["http_status"], 409)

        # Step 6: Employee cancels pending request
        cancel_res = cancel_pending_quota_request(tool_context=ctx)
        self.assertEqual(cancel_res["status"], "cancelled")
        self.assertEqual(cancel_res["request_id"], req_id)

    def test_namespaced_state_management(self) -> None:
        """Verify ADK namespaced state keys (user:*, session:*) and plain keys are populated and maintained."""
        backend = FakePortalBackend()
        set_custom_http_requester(backend.handle_request)

        ctx = ToolContext(state={})
        status_res = get_my_quota_status(user_email="alex.morgan@example.com", tool_context=ctx)
        self.assertEqual(status_res["status"], "success")
        self.assertEqual(status_res["account_status"], "AUTO_DISABLED")

        # Assert ADK namespaced keys are populated
        self.assertEqual(ctx.state.get("user:email"), "alex.morgan@example.com")
        self.assertEqual(ctx.state.get("resolved_user_email"), "alex.morgan@example.com")
        self.assertEqual(ctx.state.get("current_quota_usd"), 6.00)

        # Verify options tool reads user:preferred_option if present
        ctx.state["user:preferred_option"] = 2
        options_res = get_quota_request_options(tool_context=ctx)
        opt2 = next(opt for opt in options_res["preset_options"] if opt["option_number"] == 2)
        self.assertTrue(opt2.get("user_preferred"))

        # Submit quota request with preset option 2
        submit_res = submit_quota_increase_request(
            requested_quota_usd=2,
            reason_category="SPRINT_DEADLINE",
            justification="Sprint delivery",
            tool_context=ctx,
        )
        self.assertEqual(submit_res["status"], "submitted")
        self.assertEqual(ctx.state.get("user:preferred_option"), 2)
        self.assertEqual(ctx.state.get("user:last_reason_category"), "SPRINT_DEADLINE")

    def test_normalization_helpers_and_active_user_diagnostics(self) -> None:
        """Verify category/duration normalization and active user diagnostic formatting."""
        self.assertEqual(normalize_reason_category("production outage hotfix"), "INCIDENT")
        self.assertEqual(normalize_reason_category("codebase refactoring"), "REFACTORING")
        self.assertEqual(normalize_reason_category("new team role"), "ROLE_UPGRADE")
        self.assertEqual(normalize_duration("permanent tier"), "PERMANENT")
        self.assertEqual(normalize_duration("rest of week"), "TEMPORARY_WEEKLY")

        # Check Alice (ACTIVE)
        ctx_alice = ToolContext(state={"user_email": "alice.chen@example.com"})
        alice_status = get_my_quota_status(tool_context=ctx_alice)
        self.assertFalse(alice_status["is_paused"])
        self.assertIn("currently active", alice_status["suggested_reply"])

    def test_portal_auth_headers_and_audience(self) -> None:
        """Verify audience resolution and header injection across Cloud Run, IAP, and Proxies."""
        import os

        # 1. Default Cloud Run audience matches base URL
        self.assertEqual(
            resolve_portal_oidc_audience("https://portal-xyz.a.run.app/"),
            "https://portal-xyz.a.run.app",
        )

        # 2. IAP Client ID override
        orig_iap = os.environ.get("PORTAL_IAP_CLIENT_ID")
        orig_extra = os.environ.get("PORTAL_EXTRA_HEADERS_JSON")
        orig_proxy_hdr = os.environ.get("PORTAL_USE_PROXY_AUTH_HEADER")
        try:
            # 2. IAP Client ID override
            os.environ["PORTAL_IAP_CLIENT_ID"] = "123456789-abcdef.apps.googleusercontent.com"
            self.assertEqual(
                resolve_portal_oidc_audience("https://quota.demo.example.com"),
                "123456789-abcdef.apps.googleusercontent.com",
            )
            # 2b. Direct Cloud Run fallback overrides IAP Client ID when force_direct_audience=True
            self.assertEqual(
                resolve_portal_oidc_audience(
                    "https://portal-xyz.a.run.app/",
                    force_direct_audience=True,
                ),
                "https://portal-xyz.a.run.app",
            )

            # 3. Custom proxy headers injection
            os.environ["PORTAL_EXTRA_HEADERS_JSON"] = json.dumps({"X-Enterprise-Forwarded-Host": "portal.demo.local"})
            headers = build_portal_auth_headers(
                target_user_email="alex.morgan@example.com",
                portal_base_url="http://localhost:8080",
            )
            self.assertEqual(headers["X-Impersonate-User"], "alex.morgan@example.com")
            self.assertEqual(headers["X-Enterprise-Forwarded-Host"], "portal.demo.local")
        finally:
            if orig_iap is not None:
                os.environ["PORTAL_IAP_CLIENT_ID"] = orig_iap
            else:
                os.environ.pop("PORTAL_IAP_CLIENT_ID", None)
            if orig_extra is not None:
                os.environ["PORTAL_EXTRA_HEADERS_JSON"] = orig_extra
            else:
                os.environ.pop("PORTAL_EXTRA_HEADERS_JSON", None)
            if orig_proxy_hdr is not None:
                os.environ["PORTAL_USE_PROXY_AUTH_HEADER"] = orig_proxy_hdr
            else:
                os.environ.pop("PORTAL_USE_PROXY_AUTH_HEADER", None)

    def test_agent_engine_deployment_dry_run(self) -> None:
        """Verify Agent Engine deployment script constructs a valid ReasoningEngine plan."""
        res = deploy_to_agent_engine(
            project_id="enterprise-gemini-prod",
            location="us-central1",
            staging_bucket="gs://enterprise-gemini-prod-staging",
            portal_api_url="https://antigravity-quota-portal-xyz.a.run.app",
            concierge_sa_email="antigravity-concierge@enterprise-gemini-prod.iam.gserviceaccount.com",
            dry_run=True,
        )
        self.assertEqual(res["status"], "dry_run")
        plan = res["deployment_plan"]
        self.assertEqual(plan["root_agent_name"], "antigravity_quota_concierge")
        self.assertEqual(plan["model"], "gemini-3.5-flash")
        self.assertEqual(plan["sub_agents"], ["quota_request_agent"])
        self.assertEqual(plan["extra_packages"], ["antigravity_quota_concierge"])
        self.assertEqual(
            plan["requirements"],
            ["google-cloud-aiplatform[agent_engines,adk]", "httpx>=0.27.0"],
        )
        self.assertEqual(
            plan["env_vars"]["PORTAL_API_BASE_URL"],
            "https://antigravity-quota-portal-xyz.a.run.app",
        )

    def test_dual_endpoint_fallback_when_switching_between_gclb_iap_and_proxy(self) -> None:
        """Verify automatic fallback to PORTAL_FALLBACK_CLOUD_RUN_URL when primary GCLB+IAP endpoint returns 502/503/403."""
        import os

        attempts: list[dict[str, str]] = []

        def flaky_primary_requester(
            method: str,
            path: str,
            headers: dict[str, str],
            json_body: dict[str, Any] | None = None,
        ) -> tuple[int, Any]:
            attempts.append(dict(headers))
            # First attempt (primary GCLB+IAP URL) fails with 503 (e.g. switched back to proxy mode or SSL warming up)
            if len(attempts) == 1:
                return 503, {"detail": "GCLB backend unavailable during mode switch"}
            # Second attempt (fallback direct Cloud Run URL) succeeds
            return self.backend.handle_request(method, path, headers, json_body)

        orig_base = os.environ.get("PORTAL_API_BASE_URL")
        orig_fallback = os.environ.get("PORTAL_FALLBACK_CLOUD_RUN_URL")
        orig_iap = os.environ.get("PORTAL_IAP_CLIENT_ID")
        try:
            os.environ["PORTAL_API_BASE_URL"] = "https://quota.demo.example.com"
            os.environ["PORTAL_FALLBACK_CLOUD_RUN_URL"] = "https://antigravity-quota-portal-xyz.a.run.app"
            os.environ["PORTAL_IAP_CLIENT_ID"] = "123456789-abcdef.apps.googleusercontent.com"
            set_custom_http_requester(flaky_primary_requester)

            ctx = ToolContext(state={"user_email": "alex.morgan@example.com"})
            res = get_my_quota_status(tool_context=ctx)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["user_email"], "alex.morgan@example.com")
            self.assertEqual(len(attempts), 2)
            self.assertNotIn("X-Portal-Fallback-Attempt", attempts[0])
            self.assertEqual(attempts[1].get("X-Portal-Fallback-Attempt"), "true")

            # Also verify deploy_to_agent_engine dry-run wires both PORTAL_IAP_CLIENT_ID and PORTAL_FALLBACK_CLOUD_RUN_URL
            deploy_res = deploy_to_agent_engine(
                project_id="enterprise-gemini-prod",
                location="us-central1",
                staging_bucket="gs://enterprise-gemini-prod-staging",
                portal_api_url="https://quota.demo.example.com",
                fallback_cloud_run_url="https://antigravity-quota-portal-xyz.a.run.app/",
                iap_client_id="123456789-abcdef.apps.googleusercontent.com",
                dry_run=True,
            )
            env_vars = deploy_res["deployment_plan"]["env_vars"]
            self.assertEqual(env_vars["PORTAL_API_BASE_URL"], "https://quota.demo.example.com")
            self.assertEqual(
                env_vars["PORTAL_FALLBACK_CLOUD_RUN_URL"],
                "https://antigravity-quota-portal-xyz.a.run.app",
            )
            self.assertEqual(
                env_vars["PORTAL_IAP_CLIENT_ID"],
                "123456789-abcdef.apps.googleusercontent.com",
            )
        finally:
            set_custom_http_requester(self.backend.handle_request)
            if orig_base is not None:
                os.environ["PORTAL_API_BASE_URL"] = orig_base
            else:
                os.environ.pop("PORTAL_API_BASE_URL", None)
            if orig_fallback is not None:
                os.environ["PORTAL_FALLBACK_CLOUD_RUN_URL"] = orig_fallback
            else:
                os.environ.pop("PORTAL_FALLBACK_CLOUD_RUN_URL", None)
            if orig_iap is not None:
                os.environ["PORTAL_IAP_CLIENT_ID"] = orig_iap
            else:
                os.environ.pop("PORTAL_IAP_CLIENT_ID", None)


if __name__ == "__main__":
    unittest.main()
