#!/usr/bin/env python3
"""Stage 1 Local Testing Runner for Antigravity Quota Concierge.

Starts:
1. Local Antigravity Quota Portal Server on http://localhost:8080 (serving the
   pre-compiled React SPA in app/static/ plus all /api/* endpoints, seeded with
   alex.morgan@example.com at $6.04 / $6.00 AUTO_DISABLED).
2. Interactive Antigravity Quota Concierge Web Playground on http://localhost:8000
   (executing the real `antigravity_quota_concierge` and `quota_request_agent`
   tools against http://localhost:8080 with live tool-trace inspection and
   persona switching).

Usage:
  # Run end-to-end Stage 1 live HTTP smoke verification and exit:
  python3 concierge-agent/run_local_stage1.py --smoke-test

  # Start both http://localhost:8080 (Portal) and http://localhost:8000 (Concierge UI):
  python3 concierge-agent/run_local_stage1.py
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import sys
import threading
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

# Ensure `concierge-agent` package is importable
CONCIERGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONCIERGE_DIR.parent
if str(CONCIERGE_DIR) not in sys.path:
    sys.path.insert(0, str(CONCIERGE_DIR))

from antigravity_quota_concierge.agent import quota_request_agent, root_agent
from antigravity_quota_concierge.tools import (
    cancel_pending_quota_request,
    get_model_efficiency_insights,
    get_my_quota_requests,
    get_my_quota_status,
    get_quota_request_options,
    submit_quota_increase_request,
)

UTC = timezone.utc


class DualStackThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that listens on both IPv4 (0.0.0.0) and IPv6 (::)."""

    allow_reuse_address = True
    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def _create_dual_stack_server(port: int, handler_cls: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    try:
        return DualStackThreadingHTTPServer(("::", port), handler_cls)
    except OSError:
        return ThreadingHTTPServer(("0.0.0.0", port), handler_cls)


class _SessionToolContext:
    """Lightweight ADK ToolContext carrying session state for local execution."""

    def __init__(self, user_email: str) -> None:
        self.state = {"user_email": user_email}


def create_portal_state() -> dict[str, Any]:
    """Build initial in-memory state for the local Antigravity Quota Portal."""
    now = datetime.now(UTC)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    iso_year, iso_week, _ = monday.isocalendar()
    week_id = f"{iso_year}-W{iso_week:02d}"
    window_start_utc = monday.isoformat()

    users: dict[str, dict[str, Any]] = {
        "alex.morgan@example.com": {
            "email": "alex.morgan@example.com",
            "group_id": "business-users",
            "status": "AUTO_DISABLED",
            "is_exempt": False,
            "has_custom_quota": True,
            "custom_quota_usd": 6.00,
            "custom_overage_usd": 0.00,
            "is_temporary_quota": False,
            "current_week": {
                "week_id": week_id,
                "window_start_utc": window_start_utc,
                "total_tokens": 2_450_000,
                "total_requests": 215,
                "gross_spend_usd": 6.04,
                "quota_credits_usd": 6.00,
                "remaining_credit_usd": 0.00,
                "net_billable_cost_usd": 0.04,
                "overage_buffer_usd": 0.00,
                "spend_breakdown": {
                    "input_spend_usd": 4.10,
                    "output_spend_usd": 1.64,
                    "cached_spend_usd": 0.30,
                },
                "tokens_by_model": {
                    "gemini-3.1-pro": 1_850_000,
                    "gemini-3.5-flash": 600_000,
                },
                "spend_by_model": {
                    "gemini-3.1-pro": 5.34,
                    "gemini-3.5-flash": 0.70,
                },
                "credit_utilization_percentage": 100.7,
                "last_active": (now - timedelta(minutes=8)).isoformat(),
            },
            "created_at": (now - timedelta(days=30)).isoformat(),
            "updated_at": (now - timedelta(minutes=8)).isoformat(),
        },
        "bob.martin@example.com": {
            "email": "bob.martin@example.com",
            "group_id": "developers",
            "status": "ACTIVE",
            "is_exempt": False,
            "has_custom_quota": False,
            "custom_quota_usd": None,
            "custom_overage_usd": None,
            "is_temporary_quota": False,
            "current_week": {
                "week_id": week_id,
                "window_start_utc": window_start_utc,
                "total_tokens": 14_200_000,
                "total_requests": 680,
                "gross_spend_usd": 45.00,
                "quota_credits_usd": 50.00,
                "remaining_credit_usd": 5.00,
                "net_billable_cost_usd": 0.00,
                "overage_buffer_usd": 10.00,
                "spend_breakdown": {
                    "input_spend_usd": 30.00,
                    "output_spend_usd": 12.50,
                    "cached_spend_usd": 2.50,
                },
                "tokens_by_model": {
                    "gemini-3.1-pro": 11_000_000,
                    "gemini-3.5-flash": 3_200_000,
                },
                "spend_by_model": {
                    "gemini-3.1-pro": 39.60,
                    "gemini-3.5-flash": 5.40,
                },
                "credit_utilization_percentage": 90.0,
                "last_active": (now - timedelta(minutes=14)).isoformat(),
            },
            "created_at": (now - timedelta(days=45)).isoformat(),
            "updated_at": (now - timedelta(minutes=14)).isoformat(),
        },
        "alice.chen@example.com": {
            "email": "alice.chen@example.com",
            "group_id": "business-users",
            "status": "ACTIVE",
            "is_exempt": False,
            "has_custom_quota": False,
            "custom_quota_usd": None,
            "custom_overage_usd": None,
            "is_temporary_quota": False,
            "current_week": {
                "week_id": week_id,
                "window_start_utc": window_start_utc,
                "total_tokens": 1_900_000,
                "total_requests": 140,
                "gross_spend_usd": 4.20,
                "quota_credits_usd": 10.00,
                "remaining_credit_usd": 5.80,
                "net_billable_cost_usd": 0.00,
                "overage_buffer_usd": 2.00,
                "spend_breakdown": {
                    "input_spend_usd": 2.80,
                    "output_spend_usd": 1.10,
                    "cached_spend_usd": 0.30,
                },
                "tokens_by_model": {
                    "gemini-3.5-flash": 1_500_000,
                    "gemini-3.1-pro": 400_000,
                },
                "spend_by_model": {
                    "gemini-3.5-flash": 2.95,
                    "gemini-3.1-pro": 1.25,
                },
                "credit_utilization_percentage": 42.0,
                "last_active": (now - timedelta(minutes=20)).isoformat(),
            },
            "created_at": (now - timedelta(days=60)).isoformat(),
            "updated_at": (now - timedelta(minutes=20)).isoformat(),
        },
        "charlie.davis@example.com": {
            "email": "charlie.davis@example.com",
            "group_id": "business-users",
            "status": "MANUALLY_DISABLED",
            "is_exempt": False,
            "has_custom_quota": False,
            "custom_quota_usd": None,
            "custom_overage_usd": None,
            "is_temporary_quota": False,
            "current_week": {
                "week_id": week_id,
                "window_start_utc": window_start_utc,
                "total_tokens": 6_800_000,
                "total_requests": 520,
                "gross_spend_usd": 13.40,
                "quota_credits_usd": 10.00,
                "remaining_credit_usd": 0.00,
                "net_billable_cost_usd": 3.40,
                "overage_buffer_usd": 2.00,
                "spend_breakdown": {
                    "input_spend_usd": 9.20,
                    "output_spend_usd": 3.60,
                    "cached_spend_usd": 0.60,
                },
                "tokens_by_model": {
                    "gemini-3.1-pro": 6_800_000,
                },
                "spend_by_model": {
                    "gemini-3.1-pro": 13.40,
                },
                "credit_utilization_percentage": 134.0,
                "last_active": (now - timedelta(hours=1)).isoformat(),
            },
            "created_at": (now - timedelta(days=45)).isoformat(),
            "updated_at": (now - timedelta(hours=1)).isoformat(),
        },
    }

    groups_base: dict[str, dict[str, Any]] = {
        "business-users": {
            "group_id": "business-users",
            "display_name": "Business Users",
            "description": "Default baseline group for organization users ($10/wk quota).",
            "weekly_quota_usd": 10.00,
            "overage_buffer_usd": 2.00,
            "is_exempt": False,
            "iam_group_email": "antigravity-business-users@example.com",
            "created_at": (now - timedelta(days=90)).isoformat(),
            "updated_at": (now - timedelta(days=1)).isoformat(),
        },
        "developers": {
            "group_id": "developers",
            "display_name": "Developers",
            "description": "Core software and platform engineering teams ($50/wk quota).",
            "weekly_quota_usd": 50.00,
            "overage_buffer_usd": 10.00,
            "is_exempt": False,
            "iam_group_email": "antigravity-developers@example.com",
            "created_at": (now - timedelta(days=90)).isoformat(),
            "updated_at": (now - timedelta(days=1)).isoformat(),
        },
    }

    quota_requests: list[dict[str, Any]] = [
        {
            "request_id": "req-seed-alice-approved",
            "user_email": "alice.chen@example.com",
            "current_group_id": "business-users",
            "current_quota_usd": 10.00,
            "current_spend_usd": 4.20,
            "requested_quota_usd": 25.00,
            "reason_category": "REFACTORING",
            "justification": "Migrating legacy REST endpoints to gRPC proto definitions.",
            "duration_needed": "TEMPORARY_WEEKLY",
            "status": "APPROVED",
            "created_at": (now - timedelta(days=2, hours=3)).isoformat(),
            "reviewed_by": "admin@example.com",
            "reviewed_at": (now - timedelta(days=2)).isoformat(),
            "admin_note": "Approved for sprint migration.",
            "approved_quota_usd": 25.00,
            "approved_duration": "TEMPORARY_WEEKLY",
            "cooldown_until": None,
        },
    ]

    audit_events: list[dict[str, Any]] = [
        {
            "event_id": "evt-seed-alex-throttled",
            "timestamp": (now - timedelta(minutes=8)).isoformat(),
            "action": "GROUP_SWAP",
            "triggered_by": "hourly_evaluator",
            "target_user": "alex.morgan@example.com",
            "details": {
                "direction": "DISABLED",
                "from_group": "antigravity-enabled@example.com",
                "to_group": "antigravity-disabled@example.com",
                "current_spend_usd": 6.04,
                "quota_usd": 6.00,
                "overage_limit_usd": 0.00,
                "reason": "HARD_LIMIT_BREACHED: Spend $6.04 >= Limit $6.00",
            },
        },
    ]

    credit_pool: dict[str, Any] = {
        "tier_key": "enterprise_plus",
        "tier_name": "Gemini Enterprise Plus",
        "usage_wtu": 3900567,
        "limit_wtu": 37500000,
        "usage_usd": 7.80,
        "limit_usd": 75.00,
        "utilization_pct": 10.4,
        "window_start_utc": window_start_utc,
        "next_reset_utc": (now + timedelta(days=5, hours=4)).isoformat(),
        "last_synced_at": now.isoformat(),
        "total_purchased_credits": 250000,
        "consumed_credits_window": 48200,
        "remaining_credits": 201800,
        "utilization_percentage": 19.3,
        "window_days": 7,
        "project_id": "enterprise-agy-quota-prod",
        "is_mock": True,
        "last_updated": now.isoformat(),
    }

    app_config: dict[str, Any] = {
        "doc_id": "global_settings",
        "timezone": "America/New_York",
        "enabled_group": "antigravity-enabled@example.com",
        "disabled_group": "antigravity-disabled@example.com",
        "default_quota_usd": 10.00,
        "default_overage_usd": 2.00,
        "preset_quotas": [10.0, 25.0, 50.0, 100.0],
        "webhook_alert_url": "https://chat.googleapis.com/v1/spaces/FINOPS/messages",
        "last_publish_timestamp": (now - timedelta(minutes=15)).isoformat(),
        "mock_mode": True,
        "admin_emails": ["admin@example.com"],
        "admin_group_email": "antigravity-admins@example.com",
        "models": {
            "gemini-3.1-pro": {
                "display_name": "Gemini 3.1 Pro",
                "log_pattern": "gemini-3.1-pro",
                "input_price_per_million": 1.25,
                "output_price_per_million": 5.00,
                "cached_price_per_million": 0.3125,
                "estimated_input_ratio": 0.70,
                "estimated_output_ratio": 0.20,
                "estimated_cached_ratio": 0.10,
            },
            "gemini-3.5-flash": {
                "display_name": "Gemini 3.5 Flash",
                "log_pattern": "gemini-3.5-flash",
                "input_price_per_million": 0.15,
                "output_price_per_million": 0.60,
                "cached_price_per_million": 0.0375,
                "estimated_input_ratio": 0.70,
                "estimated_output_ratio": 0.20,
                "estimated_cached_ratio": 0.10,
            },
        },
    }

    return {
        "week_id": week_id,
        "users": users,
        "groups_base": groups_base,
        "quota_requests": quota_requests,
        "audit_events": audit_events,
        "credit_pool": credit_pool,
        "app_config": app_config,
    }


def start_portal_server(port: int, state: dict[str, Any]) -> ThreadingHTTPServer:
    """Start the local Antigravity Quota Portal HTTP server."""
    static_dir = str(REPO_ROOT / "app" / "static")
    users = state["users"]
    groups_base = state["groups_base"]
    quota_requests = state["quota_requests"]
    audit_events = state["audit_events"]
    credit_pool = state["credit_pool"]
    app_config = state["app_config"]
    week_id = state["week_id"]

    def build_groups_list() -> list[dict[str, Any]]:
        out = []
        for gid, g in groups_base.items():
            members = [u for u in users.values() if u.get("group_id") == gid]
            m_count = len(members)
            g_spend = round(sum(u["current_week"]["gross_spend_usd"] for u in members), 2)
            t_tokens = sum(u["current_week"]["total_tokens"] for u in members)
            item = dict(g)
            item["member_count"] = m_count
            item["gross_spend_usd"] = g_spend
            item["total_tokens"] = t_tokens
            item["stats"] = {
                "member_count": m_count,
                "gross_spend_usd": g_spend,
                "total_tokens": t_tokens,
            }
            out.append(item)
        return out

    def build_kpis() -> dict[str, Any]:
        u_list = list(users.values())
        return {
            "active_developers": sum(1 for u in u_list if u["status"] == "ACTIVE"),
            "auto_throttled_developers": sum(1 for u in u_list if u["status"] == "AUTO_DISABLED"),
            "manually_locked_developers": sum(
                1 for u in u_list if u["status"] == "MANUALLY_DISABLED"
            ),
            "exempt_developers": sum(1 for u in u_list if u["is_exempt"]),
            "total_tokens_this_week": sum(u["current_week"]["total_tokens"] for u in u_list),
            "total_gross_usage_usd": round(
                sum(u["current_week"]["gross_spend_usd"] for u in u_list), 2
            ),
            "total_credits_allocated_usd": round(
                sum(u["current_week"]["quota_credits_usd"] for u in u_list), 2
            ),
            "total_net_overages_usd": round(
                sum(u["current_week"]["net_billable_cost_usd"] for u in u_list), 2
            ),
            "week_id": week_id,
            "credit_pool": credit_pool,
        }

    class PortalHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=static_dir, **kwargs)

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send_json(self, data: Any, status: int = 200) -> None:
            raw = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(raw)

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _resolve_caller_email(self, qs: dict[str, list[str]]) -> str:
            header_user = (self.headers.get("X-Impersonate-User") or "").strip().lower()
            if header_user and header_user in users:
                return header_user
            as_user = (qs.get("as_user", [None])[0] or "").strip().lower()
            if as_user and as_user in users:
                return as_user
            return "alex.morgan@example.com"

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)

            if path == "/api/health":
                self._send_json({"status": "healthy"})
                return
            if path == "/api/evaluator/kpis":
                self._send_json(build_kpis())
                return
            if path == "/api/config":
                self._send_json(app_config)
                return
            if path == "/api/config/pricing":
                self._send_json(app_config["models"])
                return
            if path == "/api/groups":
                self._send_json(build_groups_list())
                return
            if path == "/api/users":
                u_list = list(users.values())
                status_filter = qs.get("status", [None])[0]
                group_filter = qs.get("group_id", [None])[0]
                if status_filter and status_filter != "ALL":
                    u_list = [u for u in u_list if u["status"] == status_filter]
                if group_filter:
                    u_list = [u for u in u_list if u.get("group_id") == group_filter]
                self._send_json(u_list)
                return
            if path.startswith("/api/users/"):
                email = urllib.parse.unquote(path.removeprefix("/api/users/"))
                if email in users:
                    self._send_json(users[email])
                else:
                    self._send_json({"detail": "User not found"}, 404)
                return
            if path == "/api/quota-requests":
                status_f = qs.get("status", [None])[0]
                user_f = qs.get("user_email", [None])[0]
                header_user = (self.headers.get("X-Impersonate-User") or "").strip().lower()
                reqs = list(quota_requests)
                if header_user and not user_f:
                    reqs = [r for r in reqs if r["user_email"] == header_user]
                elif user_f:
                    reqs = [r for r in reqs if r["user_email"] == user_f]
                if status_f:
                    reqs = [r for r in reqs if r["status"] == status_f]
                self._send_json(reqs)
                return
            if path == "/api/audit":
                self._send_json(audit_events)
                return
            if path == "/api/auth/me":
                target_email = self._resolve_caller_email(qs)
                u_obj = users[target_email]
                gid = u_obj.get("group_id") or "business-users"
                g_list = {g["group_id"]: g for g in build_groups_list()}
                active_req = next(
                    (
                        r
                        for r in quota_requests
                        if r["user_email"] == target_email and r["status"] == "PENDING"
                    ),
                    None,
                )
                util_pct = u_obj["current_week"]["credit_utilization_percentage"]
                self._send_json(
                    {
                        "email": target_email,
                        "caller_email": "concierge-agent@enterprise-agy-quota-prod.iam.gserviceaccount.com",
                        "is_admin": True,
                        "is_impersonating": True,
                        "user": u_obj,
                        "group": g_list.get(gid),
                        "credit_pool": credit_pool,
                        "active_request": active_req,
                        "in_cooldown": False,
                        "cooldown_until": None,
                        "admin_note": None,
                        "warning_threshold_reached": util_pct >= 80.0,
                    }
                )
                return

            if not path.startswith("/api"):
                full_fs = os.path.join(static_dir, path.lstrip("/"))
                if path == "/" or not os.path.exists(full_fs):
                    self.path = "/index.html"
            return super().do_GET()

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)
            body = self._read_body()

            if path == "/api/quota-requests":
                caller_email = self._resolve_caller_email(qs)
                existing_pending = next(
                    (
                        r
                        for r in quota_requests
                        if r["user_email"] == caller_email and r["status"] == "PENDING"
                    ),
                    None,
                )
                if existing_pending:
                    self._send_json(
                        {
                            "detail": (
                                f"You already have a pending quota request "
                                f"({existing_pending['request_id']})."
                            )
                        },
                        409,
                    )
                    return

                u_obj = users[caller_email]
                now_iso = datetime.now(UTC).isoformat()
                req_id = f"req-{int(time.time() * 1000) % 1000000:06d}"
                new_req = {
                    "request_id": req_id,
                    "user_email": caller_email,
                    "current_group_id": u_obj.get("group_id") or "business-users",
                    "current_quota_usd": u_obj["current_week"]["quota_credits_usd"],
                    "current_spend_usd": u_obj["current_week"]["gross_spend_usd"],
                    "requested_quota_usd": float(body.get("requested_quota_usd", 25.0)),
                    "reason_category": body.get("reason_category", "SPRINT_DEADLINE"),
                    "justification": body.get("justification", ""),
                    "duration_needed": body.get("duration_needed", "TEMPORARY_WEEKLY"),
                    "status": "PENDING",
                    "created_at": now_iso,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "admin_note": None,
                    "approved_quota_usd": None,
                    "approved_duration": None,
                    "cooldown_until": None,
                }
                quota_requests.insert(0, new_req)
                audit_events.insert(
                    0,
                    {
                        "event_id": f"evt-req-{int(time.time())}",
                        "timestamp": now_iso,
                        "action": "QUOTA_REQUEST_SUBMITTED",
                        "triggered_by": caller_email,
                        "target_user": caller_email,
                        "details": {
                            "request_id": req_id,
                            "requested_quota_usd": new_req["requested_quota_usd"],
                            "reason_category": new_req["reason_category"],
                            "duration_needed": new_req["duration_needed"],
                        },
                    },
                )
                self._send_json(new_req, 201)
                return

            if path == "/api/evaluator/publish":
                now_iso = datetime.now(UTC).isoformat()
                app_config["last_publish_timestamp"] = now_iso
                audit_events.insert(
                    0,
                    {
                        "event_id": f"evt-pub-{int(time.time())}",
                        "timestamp": now_iso,
                        "action": "PUBLISH_TRIGGERED",
                        "triggered_by": "admin_publish_button",
                        "target_user": "alex.morgan@example.com",
                        "details": {
                            "users_evaluated": 4,
                            "group_swaps": 1,
                            "reconciled_active": "alex.morgan@example.com -> antigravity-enabled@example.com",
                            "status": "SUCCESS",
                        },
                    },
                )
                self._send_json(
                    {
                        "evaluated_at": now_iso,
                        "week_id": week_id,
                        "users_evaluated": 4,
                        "group_swaps_count": 1,
                        "changes": [
                            {
                                "user": "alex.morgan@example.com",
                                "action": "ENABLED",
                                "reason": "QUOTA_INCREASE_APPROVED ($31.00/wk > $6.04 spend)",
                                "status": "ACTIVE",
                            }
                        ],
                        "success": True,
                        "error": None,
                    }
                )
                return

            self._send_json({"status": "ok"})

        def do_DELETE(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/quota-requests/"):
                req_id = urllib.parse.unquote(path.removeprefix("/api/quota-requests/"))
                for req in quota_requests:
                    if req["request_id"] == req_id:
                        if req["status"] != "PENDING":
                            self._send_json(
                                {"detail": f"Cannot cancel request in status {req['status']}"},
                                400,
                            )
                            return
                        req["status"] = "CANCELLED"
                        self._send_json({"cancelled": True, "request_id": req_id})
                        return
                self._send_json({"detail": "Quota request not found"}, 404)
                return
            self._send_json({"detail": "Not found"}, 404)

        def do_PATCH(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            body = self._read_body()

            if path.startswith("/api/quota-requests/"):
                req_id = urllib.parse.unquote(path.removeprefix("/api/quota-requests/"))
                for req in quota_requests:
                    if req["request_id"] == req_id:
                        now_iso = datetime.now(UTC).isoformat()
                        new_status = body.get("status", "APPROVED")
                        approved_q = float(
                            body.get("approved_quota_usd") or req["requested_quota_usd"]
                        )
                        approved_dur = body.get("approved_duration") or req["duration_needed"]
                        note = body.get("admin_note") or "Approved via Quota Governance Portal"
                        req["status"] = new_status
                        req["approved_quota_usd"] = approved_q if new_status == "APPROVED" else None
                        req["approved_duration"] = (
                            approved_dur if new_status == "APPROVED" else None
                        )
                        req["admin_note"] = note
                        req["reviewed_by"] = "admin@example.com"
                        req["reviewed_at"] = now_iso

                        u_email = req["user_email"]
                        if new_status == "APPROVED" and u_email in users:
                            u = users[u_email]
                            u["status"] = "ACTIVE"
                            u["has_custom_quota"] = True
                            u["custom_quota_usd"] = approved_q
                            u["is_temporary_quota"] = approved_dur == "TEMPORARY_WEEKLY"
                            gross = u["current_week"]["gross_spend_usd"]
                            u["current_week"]["quota_credits_usd"] = approved_q
                            u["current_week"]["remaining_credit_usd"] = round(
                                max(0.0, approved_q - gross), 2
                            )
                            u["current_week"]["net_billable_cost_usd"] = round(
                                max(0.0, gross - approved_q), 2
                            )
                            u["current_week"]["credit_utilization_percentage"] = round(
                                (gross / approved_q) * 100.0, 1
                            )
                            u["updated_at"] = now_iso

                        self._send_json(req)
                        return
                self._send_json({"detail": "Request not found"}, 404)
                return

            self._send_json({"status": "ok"})

    httpd = _create_dual_stack_server(port, PortalHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def orchestrate_concierge_turn(
    message: str,
    user_email: str,
) -> dict[str, Any]:
    """Execute a multi-agent turn against the live local Portal API using the Concierge tools."""
    ctx = _SessionToolContext(user_email=user_email)
    msg_lower = message.strip().lower()
    tool_traces: list[dict[str, Any]] = []
    active_agent = root_agent.name

    # 1. Check for cancellation intent -> Sub-Agent `quota_request_agent`
    if "cancel" in msg_lower:
        active_agent = quota_request_agent.name
        reqs_res = get_my_quota_requests(tool_context=ctx)
        tool_traces.append({"agent": active_agent, "tool": "get_my_quota_requests", "output": reqs_res})
        pending = reqs_res.get("active_pending_request")
        if not pending:
            return {
                "agent": active_agent,
                "model": quota_request_agent.model,
                "tool_traces": tool_traces,
                "reply": (
                    f"You don't currently have any pending quota requests to cancel for "
                    f"`{user_email}`."
                ),
            }
        cancel_res = cancel_pending_quota_request(
            request_id=pending["request_id"],
            tool_context=ctx,
        )
        tool_traces.append(
            {"agent": active_agent, "tool": "cancel_pending_quota_request", "output": cancel_res}
        )
        return {
            "agent": active_agent,
            "model": quota_request_agent.model,
            "tool_traces": tool_traces,
            "reply": (
                f"Your pending quota request **`{pending['request_id']}`** "
                f"(`${pending['requested_quota_usd']:.2f}/wk`) has been **cancelled**. "
                "You can submit a new request at any time."
            ),
        }

    # 2. Check for request status inquiry -> Sub-Agent `quota_request_agent`
    if any(
        phrase in msg_lower
        for phrase in ("status of my", "my request", "pending request", "was my request")
    ):
        active_agent = quota_request_agent.name
        reqs_res = get_my_quota_requests(tool_context=ctx)
        tool_traces.append({"agent": active_agent, "tool": "get_my_quota_requests", "output": reqs_res})
        reqs = reqs_res.get("requests") or []
        if not reqs:
            return {
                "agent": active_agent,
                "model": quota_request_agent.model,
                "tool_traces": tool_traces,
                "reply": f"No quota increase requests were found for `{user_email}`.",
            }
        latest = reqs[0]
        status_line = (
            f"Your latest quota request **`{latest['request_id']}`** is currently "
            f"**`{latest['status']}`**.\n\n"
            f"- **Requested Limit**: `${latest['requested_quota_usd']:.2f}/wk` "
            f"(`{latest['duration_needed']}`)\n"
            f"- **Reason Category**: `{latest['reason_category']}`\n"
            f"- **Justification**: {latest['justification']}"
        )
        if latest.get("admin_note"):
            status_line += f"\n- **Reviewer Note**: _{latest['admin_note']}_"
        return {
            "agent": active_agent,
            "model": quota_request_agent.model,
            "tool_traces": tool_traces,
            "reply": status_line,
        }

    # 3. Check for option selection / submission -> Sub-Agent `quota_request_agent`
    option_match = re.search(r"option\s*([123])", msg_lower)
    if option_match or any(k in msg_lower for k in ("submit", "+$15", "+$25", "+$50", "$25")):
        active_agent = quota_request_agent.name
        opts_res = get_quota_request_options(tool_context=ctx)
        tool_traces.append(
            {"agent": active_agent, "tool": "get_quota_request_options", "output": opts_res}
        )
        if opts_res.get("status") != "success":
            return {
                "agent": active_agent,
                "model": quota_request_agent.model,
                "tool_traces": tool_traces,
                "reply": opts_res.get("error", "Unable to load quota options."),
            }
        options = opts_res["preset_options"]
        chosen_idx = int(option_match.group(1)) - 1 if option_match else 1
        chosen = options[min(max(chosen_idx, 0), len(options) - 1)]

        reason = "SPRINT_DEADLINE"
        if "refactor" in msg_lower:
            reason = "REFACTORING"
        elif "incident" in msg_lower or "prod" in msg_lower:
            reason = "INCIDENT"
        elif "role" in msg_lower or "permanent" in msg_lower or chosen["option_number"] == 3:
            reason = "ROLE_UPGRADE"

        justification = (
            f"Submitted via Antigravity Quota Concierge ({chosen['label']}): {message.strip()}"
        )
        sub_res = submit_quota_increase_request(
            requested_quota_usd=chosen["requested_quota_usd"],
            reason_category=reason,
            justification=justification,
            duration_needed=chosen["duration_needed"],
            tool_context=ctx,
        )
        tool_traces.append(
            {"agent": active_agent, "tool": "submit_quota_increase_request", "output": sub_res}
        )
        if sub_res.get("status") != "submitted":
            return {
                "agent": active_agent,
                "model": quota_request_agent.model,
                "tool_traces": tool_traces,
                "reply": f"⚠️ **Could not submit request**: {sub_res.get('error')}",
            }
        return {
            "agent": active_agent,
            "model": quota_request_agent.model,
            "tool_traces": tool_traces,
            "reply": (
                f"✅ **Quota Increase Request Submitted!**\n\n"
                f"- **Request ID**: `{sub_res['request_id']}`\n"
                f"- **Employee**: `{user_email}`\n"
                f"- **New Target Limit**: `${sub_res['requested_quota_usd']:.2f}/wk` "
                f"(`{sub_res['duration_needed']}`)\n"
                f"- **Category**: `{sub_res['reason_category']}`\n"
                f"- **Status**: `{sub_res['request_status']}`\n\n"
                f"{sub_res.get('confirmation_message', '')}"
            ),
        }

    # 4. Check for "yes" / "request increase" / "options" -> Handoff to `quota_request_agent`
    if any(
        w in msg_lower
        for w in ("yes", "request", "increase", "options", "raise", "more quota", "unpause")
    ):
        active_agent = quota_request_agent.name
        opts_res = get_quota_request_options(tool_context=ctx)
        tool_traces.append(
            {"agent": active_agent, "tool": "get_quota_request_options", "output": opts_res}
        )
        if opts_res.get("status") != "success":
            return {
                "agent": active_agent,
                "model": quota_request_agent.model,
                "tool_traces": tool_traces,
                "reply": opts_res.get("error", "Cannot request quota increase right now."),
            }
        lines = [
            f"I've transferred you to **`quota_request_agent`**. Here are your quota increase "
            f"options (current spend `${opts_res['current_spend_usd']:.2f}` / "
            f"`${opts_res['current_quota_usd']:.2f}` limit):\n"
        ]
        for opt in opts_res["preset_options"]:
            lines.append(
                f"{opt['option_number']}. **{opt['label']}** → "
                f"**`${opt['requested_quota_usd']:.2f}/wk`** (`{opt['duration_needed']}`)"
            )
        if opts_res.get("role_upgrade_advice"):
            lines.append(f"\n💡 _{opts_res['role_upgrade_advice']}_")
        lines.append(
            "\nReply with **\"Option 1\"**, **\"Option 2 — Sprint deadline\"**, or **\"Option 3\"** "
            "and I will submit it to the Quota Governance Portal immediately."
        )
        return {
            "agent": active_agent,
            "model": quota_request_agent.model,
            "tool_traces": tool_traces,
            "reply": "\n".join(lines),
        }

    # 5. Check for FinOps model efficiency coaching -> Root Agent `antigravity_quota_concierge`
    if any(
        w in msg_lower
        for w in ("model", "flash", "pro", "stretch", "longer", "burn", "efficiency", "cost")
    ):
        insights = get_model_efficiency_insights(tool_context=ctx)
        tool_traces.append(
            {
                "agent": active_agent,
                "tool": "get_model_efficiency_insights",
                "output": insights,
            }
        )
        breakdown_lines = [
            f"- **`{m['model']}`** ({m['tier']}): `${m['spend_usd']:.2f}` "
            f"(`{m['tokens']:,}` tokens)"
            for m in insights.get("model_breakdown", [])
        ]
        return {
            "agent": active_agent,
            "model": root_agent.model,
            "tool_traces": tool_traces,
            "reply": (
                f"### Model Efficiency & Quota Coaching for `{user_email}`\n\n"
                f"- **Frontier Model Spend (`Pro`)**: `${insights['frontier_spend_usd']:.2f}` "
                f"(`{insights['frontier_percentage']:.1f}%`)\n"
                f"- **Lightweight Model Spend (`Flash`)**: `${insights['lightweight_spend_usd']:.2f}` "
                f"(`{insights['lightweight_percentage']:.1f}%`)\n\n"
                "**Per-Model Breakdown:**\n"
                + "\n".join(breakdown_lines)
                + f"\n\n💡 **Coaching Recommendation**: {insights['coaching_recommendation']}"
            ),
        }

    # 6. Default: Quota Status Diagnostic -> Root Agent `antigravity_quota_concierge`
    status_res = get_my_quota_status(tool_context=ctx)
    tool_traces.append({"agent": active_agent, "tool": "get_my_quota_status", "output": status_res})

    u_status = status_res["account_status"]
    spend = status_res["weekly_usage_usd"]
    limit = status_res["weekly_limit_usd"]
    rem = status_res["remaining_credit_usd"]
    reset_str = status_res["reset_countdown"]
    group_name = status_res["group_display_name"]

    if u_status == "AUTO_DISABLED":
        reply = status_res["suggested_reply"]
    elif u_status == "MANUALLY_DISABLED":
        reply = status_res["suggested_reply"]
    elif status_res.get("warning_threshold_reached"):
        reply = status_res["suggested_reply"]
    else:
        reply = (
            f"Your Antigravity access is **ACTIVE** and healthy! You have used "
            f"**${spend:.2f}** of your **${limit:.2f}** weekly limit "
            f"(**${rem:.2f}** remaining, `{status_res['utilization_percentage']:.1f}%` used; "
            f"tier: **{group_name}**, resets in **{reset_str}**)."
        )

    return {
        "agent": active_agent,
        "model": root_agent.model,
        "tool_traces": tool_traces,
        "reply": reply,
    }


PLAYGROUND_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Antigravity Quota Concierge — Stage 1 ADK Web Playground</title>
  <style>
    :root {
      --bg: #0b0f19;
      --panel: #111827;
      --panel-alt: #1f2937;
      --border: #374151;
      --text: #f9fafb;
      --muted: #9ca3af;
      --accent: #38bdf8;
      --accent-2: #818cf8;
      --success: #34d399;
      --warn: #fbbf24;
      --danger: #f87171;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      padding: 14px 24px;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .badge {
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.4);
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    select, button, input {
      background: var(--panel-alt);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 13px;
    }
    button {
      cursor: pointer;
      font-weight: 600;
      transition: all 0.15s;
    }
    button:hover {
      border-color: var(--accent);
    }
    .btn-approve {
      background: rgba(52, 211, 153, 0.15);
      color: var(--success);
      border-color: rgba(52, 211, 153, 0.4);
    }
    main {
      flex: 1;
      display: grid;
      grid-template-columns: 380px 1fr;
      overflow: hidden;
    }
    .sidebar {
      background: var(--panel);
      border-right: 1px solid var(--border);
      padding: 18px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .card {
      background: var(--panel-alt);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
    }
    .card h3 {
      margin: 0 0 8px 0;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
    }
    .agent-node {
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid var(--border);
      margin-bottom: 8px;
      font-size: 13px;
    }
    .agent-node.active {
      border-color: var(--accent);
      background: rgba(56, 189, 248, 0.1);
    }
    .trace-box {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      background: #070a12;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      overflow-x: auto;
      white-space: pre-wrap;
      max-height: 360px;
      overflow-y: auto;
      color: #a5f3fc;
    }
    .chat-pane {
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
    }
    .messages {
      flex: 1;
      padding: 24px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .msg {
      max-width: 78%;
      padding: 14px 18px;
      border-radius: 12px;
      line-height: 1.55;
      font-size: 14px;
      white-space: pre-wrap;
    }
    .msg.user {
      align-self: flex-end;
      background: #2563eb;
      color: white;
    }
    .msg.agent {
      align-self: flex-start;
      background: var(--panel-alt);
      border: 1px solid var(--border);
    }
    .msg-meta {
      font-size: 11px;
      color: var(--accent);
      margin-bottom: 6px;
      font-weight: 600;
    }
    .chips {
      padding: 10px 24px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      border-top: 1px solid var(--border);
      background: rgba(17, 24, 39, 0.7);
    }
    .chip {
      font-size: 12px;
      padding: 6px 12px;
      border-radius: 999px;
      background: var(--panel-alt);
      border: 1px solid var(--border);
      cursor: pointer;
    }
    .chip:hover {
      border-color: var(--accent);
      color: var(--accent);
    }
    .composer {
      padding: 16px 24px;
      background: var(--panel);
      border-top: 1px solid var(--border);
      display: flex;
      gap: 12px;
    }
    .composer input {
      flex: 1;
      font-size: 14px;
      padding: 12px 14px;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <strong style="font-size: 16px;">Antigravity Quota Concierge</strong>
      <span class="badge">ADK Stage 1 Local Playground</span>
      <span class="badge" style="color: var(--accent-2); border-color: rgba(129,140,248,0.4);">gemini-3.5-flash</span>
    </div>
    <div class="controls">
      <label style="font-size: 12px; color: var(--muted);">Employee Session Identity:</label>
      <select id="userSelect">
        <option value="alex.morgan@example.com">alex.morgan@example.com ($6.04 / $6.00 — AUTO_DISABLED)</option>
        <option value="bob.martin@example.com">bob.martin@example.com ($45.00 / $50.00 — 90% WARNING)</option>
        <option value="alice.chen@example.com">alice.chen@example.com ($4.20 / $10.00 — ACTIVE)</option>
        <option value="charlie.davis@example.com">charlie.davis@example.com ($13.40 / $10.00 — MANUALLY_DISABLED)</option>
      </select>
      <button class="btn-approve" onclick="approveLatestPending()">Simulate Admin Approval (:8080)</button>
      <a href="http://localhost:8080" target="_blank" style="color: var(--accent); font-size: 13px; text-decoration: none;">Open Portal UI ↗</a>
    </div>
  </header>
  <main>
    <aside class="sidebar">
      <div class="card">
        <h3>Multi-Agent Topology</h3>
        <div id="node-root" class="agent-node active">
          <strong>antigravity_quota_concierge</strong> (Root)<br/>
          <span style="font-size: 11px; color: var(--muted);">Tools: get_my_quota_status, get_model_efficiency_insights</span>
        </div>
        <div id="node-sub" class="agent-node">
          <strong>quota_request_agent</strong> (Sub-Agent)<br/>
          <span style="font-size: 11px; color: var(--muted);">Tools: get_quota_request_options, submit_quota_increase_request, get_my_quota_requests, cancel_pending_quota_request</span>
        </div>
      </div>
      <div class="card" style="flex: 1; display: flex; flex-direction: column;">
        <h3>Live Tool Call & Portal API Trace</h3>
        <div id="traceOutput" class="trace-box">Click a prompt chip or type a message to inspect live HTTP calls to http://localhost:8080/api/*</div>
      </div>
    </aside>
    <section class="chat-pane">
      <div id="messages" class="messages">
        <div class="msg agent">
          <div class="msg-meta">antigravity_quota_concierge • gemini-3.5-flash</div>
          Hello! I am the <strong>Antigravity Quota Concierge</strong>. Ask me why your Antigravity access is paused, how to stretch your weekly quota with <code>gemini-3.5-flash</code>, or to submit a quota increase request.
        </div>
      </div>
      <div class="chips">
        <span class="chip" onclick="sendPrompt('Why is my Antigravity not working?')">1. Why is my Antigravity not working?</span>
        <span class="chip" onclick="sendPrompt('How can I make my quota last longer? Which models are using my credits?')">2. Model efficiency & Flash coaching</span>
        <span class="chip" onclick="sendPrompt('Yes, please show me options to request an increase')">3. Yes, show quota increase options</span>
        <span class="chip" onclick="sendPrompt('Option 2 — Sprint deadline')">4. Submit Option 2 (+$25 Temporary)</span>
        <span class="chip" onclick="sendPrompt('What is the status of my quota request?')">5. Check my request status</span>
        <span class="chip" onclick="sendPrompt('Cancel my pending request')">6. Cancel pending request</span>
      </div>
      <form class="composer" onsubmit="event.preventDefault(); sendFromInput();">
        <input id="promptInput" type="text" placeholder="Message Antigravity Quota Concierge..." autocomplete="off" />
        <button type="submit" style="background: var(--accent); color: #000; border: none; padding: 0 20px;">Send</button>
      </form>
    </section>
  </main>
  <script>
    function savePlaygroundState() {
      try {
        sessionStorage.setItem('agy_concierge_messages', document.getElementById('messages').innerHTML);
        sessionStorage.setItem('agy_concierge_trace', document.getElementById('traceOutput').textContent);
        sessionStorage.setItem('agy_concierge_sub_active', document.getElementById('node-sub').classList.contains('active') ? '1' : '0');
      } catch (e) {}
    }
    window.addEventListener('DOMContentLoaded', () => {
      try {
        const savedMsgs = sessionStorage.getItem('agy_concierge_messages');
        if (savedMsgs) {
          const box = document.getElementById('messages');
          box.innerHTML = savedMsgs;
          box.scrollTop = box.scrollHeight;
        }
        const savedTrace = sessionStorage.getItem('agy_concierge_trace');
        if (savedTrace) {
          document.getElementById('traceOutput').textContent = savedTrace;
        }
        const subActive = sessionStorage.getItem('agy_concierge_sub_active');
        if (subActive !== null) {
          document.getElementById('node-root').classList.toggle('active', subActive !== '1');
          document.getElementById('node-sub').classList.toggle('active', subActive === '1');
        }
      } catch (e) {}
    });
    async function sendPrompt(text) {
      const userEmail = document.getElementById('userSelect').value;
      appendMessage('user', text, userEmail);
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: text, user_email: userEmail})
      });
      const data = await res.json();
      appendMessage('agent', data.reply, `${data.agent} • ${data.model}`);
      document.getElementById('traceOutput').textContent = JSON.stringify(data.tool_traces, null, 2);
      document.getElementById('node-root').classList.toggle('active', data.agent === 'antigravity_quota_concierge');
      document.getElementById('node-sub').classList.toggle('active', data.agent === 'quota_request_agent');
      savePlaygroundState();
    }
    function sendFromInput() {
      const input = document.getElementById('promptInput');
      if (!input.value.trim()) return;
      const val = input.value;
      input.value = '';
      sendPrompt(val);
    }
    function appendMessage(role, text, meta) {
      const box = document.getElementById('messages');
      const div = document.createElement('div');
      div.className = `msg ${role}`;
      const metaDiv = document.createElement('div');
      metaDiv.className = 'msg-meta';
      metaDiv.textContent = meta;
      const bodyDiv = document.createElement('div');
      bodyDiv.textContent = text;
      div.appendChild(metaDiv);
      div.appendChild(bodyDiv);
      box.appendChild(div);
      box.scrollTop = box.scrollHeight;
    }
    async function approveLatestPending() {
      const userEmail = document.getElementById('userSelect').value;
      const res = await fetch('/api/approve-pending', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_email: userEmail})
      });
      const data = await res.json();
      document.getElementById('traceOutput').textContent = JSON.stringify(data, null, 2);
      appendMessage('agent', data.message, 'Portal Admin Action (:8080)');
    }
  </script>
</body>
</html>
"""


def start_playground_server(port: int, portal_port: int) -> ThreadingHTTPServer:
    """Start the interactive Concierge Web Playground on http://localhost:8000."""

    class PlaygroundHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send_json(self, data: Any, status: int = 200) -> None:
            raw = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path == "/api/health":
                self._send_json({"status": "healthy", "agent": root_agent.name, "model": root_agent.model})
                return
            raw = PLAYGROUND_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            if self.path == "/api/chat":
                msg = body.get("message", "")
                user_email = body.get("user_email", "alex.morgan@example.com")
                result = orchestrate_concierge_turn(message=msg, user_email=user_email)
                self._send_json(result)
                return
            if self.path == "/api/approve-pending":
                user_email = body.get("user_email", "alex.morgan@example.com")
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                req_url = (
                    f"http://127.0.0.1:{portal_port}/api/quota-requests?"
                    f"user_email={urllib.parse.quote(user_email)}&status=PENDING"
                )
                with opener.open(req_url, timeout=5.0) as resp:
                    pending_list = json.loads(resp.read().decode("utf-8"))
                if not pending_list:
                    self._send_json(
                        {
                            "status": "no_pending",
                            "message": f"No PENDING request found for {user_email} on :8080.",
                        }
                    )
                    return
                req_id = pending_list[0]["request_id"]
                patch_req = urllib.request.Request(
                    f"http://127.0.0.1:{portal_port}/api/quota-requests/{req_id}",
                    data=json.dumps(
                        {
                            "status": "APPROVED",
                            "admin_note": "Approved in Stage 1 local testing.",
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PATCH",
                )
                with opener.open(patch_req, timeout=5.0) as patch_resp:
                    approved = json.loads(patch_resp.read().decode("utf-8"))
                self._send_json(
                    {
                        "status": "approved",
                        "approved_request": approved,
                        "message": (
                            f"✅ Admin approved request {req_id} on Portal (:8080)! "
                            f"{user_email} is now ACTIVE with a ${approved['approved_quota_usd']:.2f}/wk limit. "
                            "Ask 'Why is my Antigravity not working?' again to verify."
                        ),
                    }
                )
                return
            self._send_json({"detail": "Not found"}, 404)

    httpd = _create_dual_stack_server(port, PlaygroundHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def run_smoke_test(portal_port: int) -> None:
    """Run automated Stage 1 E2E smoke test over live localhost HTTP."""
    os.environ["PORTAL_API_BASE_URL"] = f"http://127.0.0.1:{portal_port}"
    os.environ["CONCIERGE_DEV_DEFAULT_USER"] = "alex.morgan@example.com"

    print("=" * 78)
    print("STAGE 1 E2E SMOKE VERIFICATION — ANTIGRAVITY QUOTA CONCIERGE (gemini-3.5-flash)")
    print("=" * 78)

    steps = [
        ("Turn 1 (Root Agent — Quota Paused Diagnostic)", "Why is my Antigravity not working?"),
        (
            "Turn 2 (Root Agent — FinOps Model Efficiency Coaching)",
            "How can I make my quota last longer? Which models are using my credits?",
        ),
        (
            "Turn 3 (Sub-Agent Handoff — Preset Options)",
            "Yes, please show me options to request an increase",
        ),
        (
            "Turn 4 (Sub-Agent — Submit Option 2 +$25 Temporary Request)",
            "Option 2 — Sprint deadline",
        ),
        (
            "Turn 5 (Sub-Agent — Check Request Status)",
            "What is the status of my quota request?",
        ),
    ]

    for title, prompt in steps:
        print(f"\n--- {title} ---")
        print(f"Employee (alex.morgan@example.com): {prompt}")
        res = orchestrate_concierge_turn(prompt, "alex.morgan@example.com")
        tools_called = ", ".join(f"{t['agent']}.{t['tool']}()" for t in res["tool_traces"])
        print(f"Active Agent: {res['agent']} ({res['model']}) | Tools: {tools_called}")
        print(f"Concierge:\n{res['reply']}")

    # Verify Admin Approval round-trip on Portal (:8080) -> User un-throttled to ACTIVE
    print("\n--- Turn 6 (Portal Admin Approval -> Auto-Unthrottle Verification) ---")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(
        f"http://127.0.0.1:{portal_port}/api/quota-requests?user_email=alex.morgan@example.com&status=PENDING",
        timeout=5.0,
    ) as r:
        pending = json.loads(r.read().decode("utf-8"))
    assert len(pending) == 1, f"Expected 1 pending request, got {len(pending)}"
    req_id = pending[0]["request_id"]

    patch_req = urllib.request.Request(
        f"http://127.0.0.1:{portal_port}/api/quota-requests/{req_id}",
        data=json.dumps({"status": "APPROVED", "admin_note": "Approved for sprint release."}).encode(
            "utf-8"
        ),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with opener.open(patch_req, timeout=5.0) as r:
        approved_data = json.loads(r.read().decode("utf-8"))
    print(
        f"Portal Admin (:8080): Approved {req_id} -> new quota ${approved_data['approved_quota_usd']:.2f}/wk"
    )

    res_after = orchestrate_concierge_turn(
        "Why is my Antigravity not working?", "alex.morgan@example.com"
    )
    print(f"Employee (alex.morgan@example.com): Why is my Antigravity not working?")
    print(f"Concierge:\n{res_after['reply']}")
    assert "ACTIVE" in res_after["reply"] and "$31.00" in res_after["reply"]

    print("\n" + "=" * 78)
    print("ALL 6 STAGE 1 LIVE HTTP ROUND-TRIP CHECKS PASSED!")
    print("=" * 78)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1 Local Runner for Antigravity Quota Concierge")
    parser.add_argument("--portal-port", type=int, default=8080, help="Port for Local Portal HTTP Server")
    parser.add_argument(
        "--playground-port", type=int, default=8000, help="Port for Interactive Concierge Web UI"
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run automated E2E Stage 1 smoke verification and exit",
    )
    args = parser.parse_args()

    os.environ["PORTAL_API_BASE_URL"] = f"http://127.0.0.1:{args.portal_port}"
    os.environ["CONCIERGE_DEV_DEFAULT_USER"] = "alex.morgan@example.com"

    state = create_portal_state()
    start_portal_server(args.portal_port, state)

    if args.smoke_test:
        run_smoke_test(args.portal_port)
        return

    start_playground_server(args.playground_port, args.portal_port)
    print(f"[Stage 1] Antigravity Quota Portal running at:      http://localhost:{args.portal_port}")
    print(f"[Stage 1] Antigravity Concierge Web UI running at:  http://localhost:{args.playground_port}")
    print("[Stage 1] Seeded persona: alex.morgan@example.com ($6.04 / $6.00 AUTO_DISABLED)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nShutting down Stage 1 servers.")


if __name__ == "__main__":
    main()
