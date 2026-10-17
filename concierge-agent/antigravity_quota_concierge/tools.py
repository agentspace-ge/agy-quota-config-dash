"""Portal API tools for the Antigravity Quota Concierge ADK Multi-Agent system.

Provides tools across the 2-agent topology:
- Root Diagnostic & Coaching Agent (`antigravity_quota_concierge`):
  1. `get_my_quota_status` — Checks the caller's email, current weekly spend, quota limit,
     throttling state, 80% pacing warning, upstream weekly reset countdown, and group tier
     via `GET /api/auth/me`.
  2. `get_model_efficiency_insights` — Analyzes `spend_by_model` and `tokens_by_model`
     (Frontier Pro/Opus/Sonnet vs Lightweight Flash split) to explain why quota ran out
     quickly and coach the developer on stretching their weekly budget 3–4x further.

- Quota Request Sub-Agent (`quota_request_agent`):
  3. `get_quota_request_options` — Presents the 3 numbered preset options (+$15 Temporary,
     +$25 Temporary [Recommended], +$50 Permanent/Role Upgrade) and 5 reason categories.
  4. `get_my_quota_requests` — Lists pending, approved, and rejected requests via
     `GET /api/quota-requests`, surfacing reviewer notes (`admin_note`) and rejection
     cooldown timers (`cooldown_until`).
  5. `submit_quota_increase_request` — Submits a quota increase request via
     `POST /api/quota-requests`.
  6. `cancel_pending_quota_request` — Withdraws an existing pending quota request via
     `DELETE /api/quota-requests/{request_id}`.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any, Callable

from antigravity_quota_concierge._adk_compat import ToolContext
from antigravity_quota_concierge.auth import (
    build_portal_auth_headers,
    resolve_employee_email,
)

logger = logging.getLogger(__name__)

REASON_CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "SPRINT_DEADLINE": "Active Sprint / Tight Deadline — Upcoming delivery deadline requiring high token throughput",
    "REFACTORING": "Heavy Refactoring / Large Context — Large codebase indexing or multi-file architecture refactor",
    "INCIDENT": "Production Incident / Hotfix — Active production outage or urgent root cause investigation",
    "ROLE_UPGRADE": "Role Change / Need Tier Upgrade — Transitioned to new team or role requiring higher baseline",
    "OTHER": "Other Project Need — Custom research, model benchmarking, or exploratory prototype",
}

DURATION_DESCRIPTIONS: dict[str, str] = {
    "TEMPORARY_WEEKLY": "Temporary (Rest of Current Week — auto-resets on weekly cycle)",
    "PERMANENT": "Permanent Weekly Override (Carries forward across future weekly resets)",
}

# Optional injectable transport for in-process testing (e.g., FastAPI TestClient or mock handler)
_custom_http_requester: Callable[[str, str, dict[str, str], dict[str, Any] | None], tuple[int, Any]] | None = None


def set_custom_http_requester(
    requester: Callable[[str, str, dict[str, str], dict[str, Any] | None], tuple[int, Any]] | None,
) -> None:
    """Register a custom HTTP requester (e.g. for unit tests or in-process ASGI calls)."""
    global _custom_http_requester
    _custom_http_requester = requester


def get_portal_base_url() -> str:
    """Return the configured base URL for the Antigravity Quota Portal service."""
    return os.environ.get("PORTAL_API_BASE_URL", "http://localhost:8080").rstrip("/")


def get_portal_fallback_url() -> str:
    """Return the optional fallback direct Cloud Run URL when switching between GCLB+IAP and proxy mode."""
    return (
        os.environ.get("PORTAL_FALLBACK_CLOUD_RUN_URL")
        or os.environ.get("PORTAL_CLOUD_RUN_URL")
        or ""
    ).strip().rstrip("/")


def _execute_single_http_request(
    method: str,
    base_url: str,
    path: str,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Execute a single HTTP request against `base_url + path`."""
    if _custom_http_requester is not None:
        return _custom_http_requester(method.upper(), path, headers, json_body)

    url = f"{base_url}{path}"
    data_bytes = json.dumps(json_body).encode("utf-8") if json_body is not None else None

    req = urllib.request.Request(url=url, data=data_bytes, headers=headers, method=method.upper())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=15.0) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return int(resp.status), parsed
    except urllib.error.HTTPError as http_err:
        raw_err = http_err.read().decode("utf-8", errors="replace")
        try:
            parsed_err = json.loads(raw_err) if raw_err else {"detail": str(http_err)}
        except Exception:
            parsed_err = {"detail": raw_err or str(http_err)}
        return int(http_err.code), parsed_err
    except Exception as exc:
        logger.error(f"Portal API call failed ({method} {url}): {exc}")
        return 503, {"detail": f"Could not reach Antigravity Quota Portal API at {base_url}: {exc}"}


def _portal_http_request(
    method: str,
    path: str,
    target_user_email: str,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Execute an authenticated HTTP request against the Antigravity Quota Portal API.

    Supports automatic dual-endpoint fallback: if `PORTAL_API_BASE_URL` (e.g. GCLB + IAP)
    returns a gateway/auth/reachability error (401, 403, 502, 503, 504) during SSL warmup
    or after switching back to `proxy` mode, and `PORTAL_FALLBACK_CLOUD_RUN_URL` is configured,
    automatically retries against the fallback direct Cloud Run URL using direct OIDC audience.
    """
    base_url = get_portal_base_url()
    headers = build_portal_auth_headers(
        target_user_email=target_user_email,
        portal_base_url=base_url,
        force_direct_audience=False,
    )
    status_code, response_data = _execute_single_http_request(
        method=method,
        base_url=base_url,
        path=path,
        headers=headers,
        json_body=json_body,
    )

    fallback_url = get_portal_fallback_url()
    if (
        status_code in (401, 403, 502, 503, 504)
        and fallback_url
        and fallback_url != base_url
    ):
        logger.warning(
            f"Primary Portal endpoint {base_url} returned HTTP {status_code}; "
            f"retrying via fallback Cloud Run URL {fallback_url}..."
        )
        fallback_headers = build_portal_auth_headers(
            target_user_email=target_user_email,
            portal_base_url=fallback_url,
            force_direct_audience=True,
        )
        fallback_headers["X-Portal-Fallback-Attempt"] = "true"
        return _execute_single_http_request(
            method=method,
            base_url=fallback_url,
            path=path,
            headers=fallback_headers,
            json_body=json_body,
        )

    return status_code, response_data


def format_reset_countdown(next_reset_utc: str | None) -> str:
    """Format an ISO-8601 UTC timestamp into a concise human countdown (`2d 14h`)."""
    if not next_reset_utc or not isinstance(next_reset_utc, str):
        return "End of weekly cycle"
    try:
        cleaned = next_reset_utc.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        target_dt = datetime.fromisoformat(cleaned)
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        diff_seconds = int((target_dt - now).total_seconds())
        if diff_seconds <= 0:
            return "Resetting soon"
        days = diff_seconds // 86400
        hours = (diff_seconds % 86400) // 3600
        minutes = (diff_seconds % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except Exception:
        return "End of weekly cycle"


def format_diagnostic_reply(auth_me_data: dict[str, Any]) -> str:
    """Format the concise diagnostic message for the employee's quota state."""
    user = auth_me_data.get("user") or {}
    current_week = user.get("current_week") or {}
    status = str(user.get("status", "ACTIVE")).upper()

    gross_spend = float(current_week.get("gross_spend_usd", 0.0))
    quota_limit = float(current_week.get("quota_credits_usd", 10.0))
    remaining_credit = max(0.0, round(quota_limit - gross_spend, 2))

    active_request = auth_me_data.get("active_request")
    in_cooldown = bool(auth_me_data.get("in_cooldown", False))
    cooldown_until = auth_me_data.get("cooldown_until")
    admin_note = auth_me_data.get("admin_note")
    warning_reached = bool(auth_me_data.get("warning_threshold_reached", False))

    if status == "AUTO_DISABLED":
        if isinstance(active_request, dict) and active_request.get("status") == "PENDING":
            req_id = active_request.get("request_id", "pending")
            req_quota = float(active_request.get("requested_quota_usd", quota_limit + 25.0))
            return (
                f"Your Antigravity access is currently paused because your weekly usage reached "
                f"${gross_spend:.2f}, which exceeds your ${quota_limit:.2f} limit. "
                f"You already have a pending quota increase request ({req_id} for ${req_quota:.2f}/wk) "
                f"awaiting review by your manager or administrator. Would you like me to cancel and replace "
                f"this pending request with different options?"
            )
        if in_cooldown:
            note_suffix = f' Admin note: "{admin_note}".' if admin_note else ""
            until_suffix = f" until {cooldown_until}" if cooldown_until else ""
            return (
                f"Your Antigravity access is currently paused because your weekly usage reached "
                f"${gross_spend:.2f}, which exceeds your ${quota_limit:.2f} limit. "
                f"A recent quota increase request was declined and cooldown is active{until_suffix}.{note_suffix}"
            )
        return (
            f"Your Antigravity access is currently paused because your weekly usage reached "
            f"${gross_spend:.2f}, which exceeds your ${quota_limit:.2f} limit. "
            f"Would you like me to submit an increase request to your manager or administrator?"
        )

    if status == "MANUALLY_DISABLED":
        return (
            f"Your Antigravity access is currently locked by an administrator "
            f"(weekly usage: ${gross_spend:.2f} of your ${quota_limit:.2f} limit). "
            f"Would you like me to submit a quota review request to your administrator?"
        )

    if warning_reached:
        return (
            f"Your Antigravity access is currently active, and your weekly usage has reached "
            f"${gross_spend:.2f} of your ${quota_limit:.2f} limit (${remaining_credit:.2f} remaining). "
            f"Would you like me to proactively submit an increase request to your manager or administrator?"
        )

    return (
        f"Your Antigravity access is currently active. Your weekly usage is "
        f"${gross_spend:.2f} of your ${quota_limit:.2f} limit (${remaining_credit:.2f} remaining). "
        f"Would you like me to submit a quota increase request to your manager or administrator?"
    )


def build_preset_options(current_quota_usd: float) -> list[dict[str, Any]]:
    """Build the 3 numbered preset quota increase options relative to `current_quota_usd`."""
    base = round(float(current_quota_usd), 2)
    opt1_total = round(base + 15.0, 2)
    opt2_total = round(base + 25.0, 2)
    opt3_total = round(base + 50.0, 2)

    return [
        {
            "option_number": 1,
            "increment_usd": 15.0,
            "requested_quota_usd": opt1_total,
            "duration_needed": "TEMPORARY_WEEKLY",
            "recommended": False,
            "label": f"Option 1: +$15.00 Temporary Boost (New weekly limit: ${opt1_total:.2f} for the rest of this week)",
        },
        {
            "option_number": 2,
            "increment_usd": 25.0,
            "requested_quota_usd": opt2_total,
            "duration_needed": "TEMPORARY_WEEKLY",
            "recommended": True,
            "label": (
                f"Option 2 (Recommended): +$25.00 Temporary Boost "
                f"(New weekly limit: ${opt2_total:.2f} for the rest of this week)"
            ),
        },
        {
            "option_number": 3,
            "increment_usd": 50.0,
            "requested_quota_usd": opt3_total,
            "duration_needed": "PERMANENT",
            "recommended": False,
            "label": (
                f"Option 3: +$50.00 Permanent Upgrade "
                f"(New weekly limit: ${opt3_total:.2f} ongoing, or specify a custom dollar amount)"
            ),
        },
    ]


def normalize_reason_category(raw_category: str) -> str:
    """Normalize a user-provided or LLM-provided reason category to a valid enum value."""
    if not raw_category:
        return "SPRINT_DEADLINE"
    cleaned = raw_category.strip().upper().replace("-", "_").replace(" ", "_")
    if cleaned in REASON_CATEGORY_DESCRIPTIONS:
        return cleaned

    lower = raw_category.strip().lower()
    if any(k in lower for k in ("sprint", "deadline", "delivery", "release", "milestone")):
        return "SPRINT_DEADLINE"
    if any(k in lower for k in ("refactor", "migration", "context", "codebase", "index")):
        return "REFACTORING"
    if any(k in lower for k in ("incident", "outage", "hotfix", "prod", "sev", "emergency", "bug")):
        return "INCIDENT"
    if any(k in lower for k in ("role", "tier", "team", "upgrade", "promotion", "permanent")):
        return "ROLE_UPGRADE"
    return "OTHER"


def normalize_duration(raw_duration: str) -> str:
    """Normalize duration string into `TEMPORARY_WEEKLY` or `PERMANENT`."""
    if not raw_duration:
        return "TEMPORARY_WEEKLY"
    cleaned = raw_duration.strip().upper().replace("-", "_").replace(" ", "_")
    if cleaned in DURATION_DESCRIPTIONS:
        return cleaned
    lower = raw_duration.strip().lower()
    if any(k in lower for k in ("perm", "ongoing", "forever", "always", "tier")):
        return "PERMANENT"
    return "TEMPORARY_WEEKLY"


def get_my_quota_status(
    user_email: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Check the employee's Antigravity access status, weekly usage, reset countdown, and group tier.

    Calls `GET /api/auth/me` on the Antigravity Quota Portal for the authenticated
    employee and returns their current status (`ACTIVE`, `AUTO_DISABLED`, or
    `MANUALLY_DISABLED`), weekly spend (`gross_spend_usd`), weekly limit
    (`quota_credits_usd`), weekly reset countdown (`reset_countdown`), group tier,
    active pending requests, and a `suggested_reply`.

    Args:
        user_email: Optional email override (if not provided, resolved automatically
            from Gemini Enterprise OAuth/session context).
        tool_context: ADK ToolContext injected automatically by the ADK runner.
    """
    resolved_email = resolve_employee_email(tool_context=tool_context, explicit_email=user_email)
    if not resolved_email:
        return {
            "status": "missing_identity",
            "suggested_reply": (
                "I couldn't automatically detect your corporate email address from this session. "
                "Could you please share your corporate email address so I can check your Antigravity quota and status?"
            ),
            "error": "No authenticated user email found in session.",
        }

    status_code, data = _portal_http_request("GET", "/api/auth/me", target_user_email=resolved_email)

    if status_code != 200 or not isinstance(data, dict):
        detail = data.get("detail") if isinstance(data, dict) else str(data)
        return {
            "status": "error",
            "http_status": status_code,
            "user_email": resolved_email,
            "error": f"Failed to retrieve quota status for {resolved_email}: {detail}",
        }

    user_obj = data.get("user") or {}
    current_week = user_obj.get("current_week") or {}
    group_obj = data.get("group") or {}
    credit_pool = data.get("credit_pool") or {}
    active_req = data.get("active_request")

    gross_spend = round(float(current_week.get("gross_spend_usd", 0.0)), 2)
    quota_limit = round(float(current_week.get("quota_credits_usd", 10.0)), 2)
    overage_buffer = round(float(current_week.get("overage_buffer_usd", 2.0)), 2)
    remaining_credit = max(0.0, round(quota_limit - gross_spend, 2))
    utilization_pct = round(float(current_week.get("credit_utilization_percentage", 0.0)), 1)
    user_status = str(user_obj.get("status", "ACTIVE"))
    group_id = str(user_obj.get("group_id") or group_obj.get("group_id") or "business-users")
    group_display_name = str(group_obj.get("display_name") or "Business Users")
    is_default_business_tier = group_id.lower() == "business-users"
    next_reset_utc = credit_pool.get("next_reset_utc")
    reset_countdown = format_reset_countdown(next_reset_utc)
    warning_reached = bool(data.get("warning_threshold_reached", False)) or (
        user_status == "ACTIVE" and utilization_pct >= 80.0
    )

    suggested_reply = format_diagnostic_reply(data)

    if tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
        tool_context.state["user:email"] = resolved_email
        tool_context.state["resolved_user_email"] = resolved_email
        tool_context.state["current_quota_usd"] = quota_limit
        tool_context.state["current_spend_usd"] = gross_spend
        tool_context.state["user_status"] = user_status
        tool_context.state["group_id"] = group_id
        tool_context.state["spend_by_model"] = current_week.get("spend_by_model") or {}
        tool_context.state["tokens_by_model"] = current_week.get("tokens_by_model") or {}
        tool_context.state["active_request_id"] = active_req.get("request_id") if isinstance(active_req, dict) else None

    return {
        "status": "success",
        "user_email": resolved_email,
        "is_admin": bool(data.get("is_admin", False)),
        "account_status": user_status,
        "is_paused": user_status in ("AUTO_DISABLED", "MANUALLY_DISABLED"),
        "is_exempt": bool(user_obj.get("is_exempt", False)),
        "is_temporary_quota": bool(user_obj.get("is_temporary_quota", False)),
        "warning_threshold_reached": warning_reached,
        "weekly_usage_usd": gross_spend,
        "weekly_limit_usd": quota_limit,
        "overage_buffer_usd": overage_buffer,
        "hard_cap_usd": round(quota_limit + overage_buffer, 2),
        "remaining_credit_usd": remaining_credit,
        "utilization_percentage": utilization_pct,
        "group_id": group_id,
        "group_display_name": group_display_name,
        "is_default_business_tier": is_default_business_tier,
        "spend_by_model": current_week.get("spend_by_model") or {},
        "tokens_by_model": current_week.get("tokens_by_model") or {},
        "next_reset_utc": next_reset_utc,
        "reset_countdown": reset_countdown,
        "active_request": active_req,
        "in_cooldown": bool(data.get("in_cooldown", False)),
        "cooldown_until": data.get("cooldown_until"),
        "admin_note": data.get("admin_note"),
        "suggested_reply": suggested_reply,
    }


def get_model_efficiency_insights(
    user_email: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Analyze the employee's model-by-model spend and provide FinOps efficiency coaching.

    Computes Frontier (`Pro`/`Opus`/`Sonnet`) vs Lightweight (`Flash`) spend percentages
    from `spend_by_model` and `tokens_by_model`, explaining why quota was consumed rapidly
    and how switching routine tasks to `gemini-3.5-flash` stretches weekly quota 3–4x further.

    Args:
        user_email: Optional email override.
        tool_context: ADK ToolContext injected automatically by the ADK runner.
    """
    resolved_email = resolve_employee_email(tool_context=tool_context, explicit_email=user_email)
    status_info = get_my_quota_status(user_email=resolved_email, tool_context=tool_context)
    if status_info.get("status") != "success":
        return status_info

    spend_by_model: dict[str, Any] = status_info.get("spend_by_model") or {}
    tokens_by_model: dict[str, Any] = status_info.get("tokens_by_model") or {}
    all_models = sorted(set(list(spend_by_model.keys()) + list(tokens_by_model.keys())))

    frontier_spend = 0.0
    lightweight_spend = 0.0
    total_model_spend = 0.0
    model_breakdown: list[dict[str, Any]] = []

    for model_name in all_models:
        spend = round(float(spend_by_model.get(model_name, 0.0)), 2)
        tokens = int(tokens_by_model.get(model_name, 0))
        total_model_spend += spend
        lower = model_name.lower()
        is_frontier = any(k in lower for k in ("pro", "sonnet", "opus", "o1", "o3"))
        if is_frontier:
            frontier_spend += spend
        else:
            lightweight_spend += spend
        model_breakdown.append(
            {
                "model": model_name,
                "tier": "frontier" if is_frontier else "lightweight",
                "spend_usd": spend,
                "tokens": tokens,
            }
        )

    model_breakdown.sort(key=lambda item: item["spend_usd"], reverse=True)
    frontier_pct = round((frontier_spend / total_model_spend) * 100.0, 1) if total_model_spend > 0 else 0.0
    lightweight_pct = round((lightweight_spend / total_model_spend) * 100.0, 1) if total_model_spend > 0 else 0.0

    top_model = model_breakdown[0]["model"] if model_breakdown else "gemini-3-pro"
    top_model_spend = model_breakdown[0]["spend_usd"] if model_breakdown else 0.0

    if frontier_pct >= 70.0 and total_model_spend > 0:
        coaching_recommendation = (
            f"{frontier_pct:.0f}% of your weekly spend (${frontier_spend:.2f} of ${total_model_spend:.2f}, "
            f"led by `{top_model}` at ${top_model_spend:.2f}) came from Frontier reasoning models. "
            f"Switching routine code edits, unit test generation, and quick Q&A to `gemini-3.5-flash` "
            f"reduces token cost by ~75%, allowing your ${status_info['weekly_limit_usd']:.2f} weekly quota "
            f"to last 3–4x longer while reserving Pro models for complex multi-file architecture tasks."
        )
    elif total_model_spend > 0:
        coaching_recommendation = (
            f"Your model mix is well-balanced ({lightweight_pct:.0f}% Lightweight Flash models vs "
            f"{frontier_pct:.0f}% Frontier models across ${total_model_spend:.2f} total spend). "
            f"Continuing to use `gemini-3.5-flash` for high-frequency iterations keeps token burn low."
        )
    else:
        coaching_recommendation = (
            "You have $0.00 recorded model spend so far this week. Using `gemini-3.5-flash` for "
            "routine coding and reserving Frontier Pro models for complex design work will maximize your weekly budget."
        )

    return {
        "status": "success",
        "user_email": resolved_email,
        "weekly_usage_usd": status_info["weekly_usage_usd"],
        "weekly_limit_usd": status_info["weekly_limit_usd"],
        "frontier_spend_usd": round(frontier_spend, 2),
        "lightweight_spend_usd": round(lightweight_spend, 2),
        "frontier_percentage": frontier_pct,
        "lightweight_percentage": lightweight_pct,
        "model_breakdown": model_breakdown,
        "coaching_recommendation": coaching_recommendation,
    }


def get_quota_request_options(
    user_email: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Retrieve available quota increase preset options and reason categories for the employee.

    Returns the 3 numbered preset options (+$15 Temporary, +$25 Temporary [Recommended],
    +$50 Permanent/Custom) computed from the employee's current weekly quota, plus the
    5 supported business reason categories and group role-upgrade guidance.

    Args:
        user_email: Optional email override.
        tool_context: ADK ToolContext injected automatically by the ADK runner.
    """
    resolved_email = resolve_employee_email(tool_context=tool_context, explicit_email=user_email)
    if not resolved_email:
        return {
            "status": "missing_identity",
            "error": "Could not identify your enterprise account. Please specify your corporate email address.",
        }

    current_quota: float | None = None
    current_spend: float = 0.0
    group_id: str = "business-users"
    active_request_id: str | None = None

    if tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
        if tool_context.state.get("resolved_user_email") == resolved_email:
            current_quota = tool_context.state.get("current_quota_usd")
            current_spend = float(tool_context.state.get("current_spend_usd") or 0.0)
            group_id = str(tool_context.state.get("group_id") or "business-users")
            active_request_id = tool_context.state.get("active_request_id")

    if current_quota is None:
        status_info = get_my_quota_status(user_email=resolved_email, tool_context=tool_context)
        if status_info.get("status") == "success":
            current_quota = float(status_info["weekly_limit_usd"])
            current_spend = float(status_info["weekly_usage_usd"])
            group_id = str(status_info.get("group_id") or "business-users")
            active_req = status_info.get("active_request")
            active_request_id = active_req.get("request_id") if isinstance(active_req, dict) else None
        else:
            current_quota = 10.0

    presets = build_preset_options(current_quota)
    preferred_option = None
    if tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
        pref = tool_context.state.get("user:preferred_option")
        if pref is not None:
            try:
                preferred_option = int(pref)
            except (ValueError, TypeError):
                preferred_option = None

    if preferred_option is not None:
        for opt in presets:
            opt["user_preferred"] = (opt.get("option_number") == preferred_option)

    role_upgrade_advice = None
    if group_id.lower() == "business-users":
        role_upgrade_advice = (
            "You are currently assigned to the default 'Business Users' tier. If you are a full-time "
            "software engineer needing the standard $50.00/wk developer baseline, select Option 3 "
            "(+$50.00 Permanent Upgrade) with reason category 'ROLE_UPGRADE'."
        )

    return {
        "status": "success",
        "user_email": resolved_email,
        "group_id": group_id,
        "current_quota_usd": round(float(current_quota), 2),
        "current_spend_usd": round(float(current_spend), 2),
        "active_pending_request_id": active_request_id,
        "preset_options": presets,
        "reason_categories": [
            {"code": code, "description": desc} for code, desc in REASON_CATEGORY_DESCRIPTIONS.items()
        ],
        "durations": [{"code": code, "description": desc} for code, desc in DURATION_DESCRIPTIONS.items()],
        "role_upgrade_advice": role_upgrade_advice,
    }


def get_my_quota_requests(
    user_email: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Retrieve the employee's quota request history, pending status, reviewer notes, and cooldowns.

    Calls `GET /api/quota-requests` and `GET /api/auth/me` to list all pending, approved,
    and rejected quota requests for the employee, including reviewer `admin_note` and
    post-rejection `cooldown_until` timers.

    Args:
        user_email: Optional email override.
        tool_context: ADK ToolContext injected automatically by the ADK runner.
    """
    resolved_email = resolve_employee_email(tool_context=tool_context, explicit_email=user_email)
    status_code, req_list = _portal_http_request(
        "GET",
        f"/api/quota-requests?user_email={resolved_email}",
        target_user_email=resolved_email,
    )

    if status_code != 200 or not isinstance(req_list, list):
        detail = req_list.get("detail") if isinstance(req_list, dict) else str(req_list)
        return {
            "status": "error",
            "http_status": status_code,
            "user_email": resolved_email,
            "error": f"Failed to retrieve quota requests for {resolved_email}: {detail}",
        }

    status_info = get_my_quota_status(user_email=resolved_email, tool_context=tool_context)
    in_cooldown = bool(status_info.get("in_cooldown", False)) if isinstance(status_info, dict) else False
    cooldown_until = status_info.get("cooldown_until") if isinstance(status_info, dict) else None
    admin_note = status_info.get("admin_note") if isinstance(status_info, dict) else None

    pending = [r for r in req_list if isinstance(r, dict) and r.get("status") == "PENDING"]
    approved = [r for r in req_list if isinstance(r, dict) and r.get("status") == "APPROVED"]
    rejected = [r for r in req_list if isinstance(r, dict) and r.get("status") == "REJECTED"]

    return {
        "status": "success",
        "user_email": resolved_email,
        "total_requests": len(req_list),
        "pending_count": len(pending),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "active_pending_request": pending[0] if pending else None,
        "in_cooldown": in_cooldown,
        "cooldown_until": cooldown_until,
        "cooldown_countdown": format_reset_countdown(cooldown_until) if cooldown_until else None,
        "latest_admin_note": admin_note,
        "requests": req_list,
    }


def submit_quota_increase_request(
    requested_quota_usd: float,
    reason_category: str = "SPRINT_DEADLINE",
    justification: str = "",
    duration_needed: str = "TEMPORARY_WEEKLY",
    user_email: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Submit a quota increase request to the Antigravity Quota Portal (`POST /api/quota-requests`).

    Args:
        requested_quota_usd: Either the target total weekly quota in USD (e.g., 35.0),
            a preset option number (1, 2, or 3), or an increment (+15, +25, +50).
            If an option number (1, 2, 3) or an increment <= current_quota_usd is passed,
            it is automatically converted to `current_quota_usd + increment`.
        reason_category: One of `SPRINT_DEADLINE`, `REFACTORING`, `INCIDENT`,
            `ROLE_UPGRADE`, or `OTHER` (natural language descriptions are also mapped).
        justification: Business justification explaining why the increase is needed.
        duration_needed: Either `TEMPORARY_WEEKLY` (rest of current week) or `PERMANENT`.
        user_email: Optional email override.
        tool_context: ADK ToolContext injected automatically by the ADK runner.
    """
    resolved_email = resolve_employee_email(tool_context=tool_context, explicit_email=user_email)
    if not resolved_email:
        return {
            "status": "missing_identity",
            "error": "Could not identify your enterprise account. Please specify your corporate email address.",
        }

    current_quota: float | None = None
    if tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
        if tool_context.state.get("resolved_user_email") == resolved_email:
            current_quota = tool_context.state.get("current_quota_usd")

    if current_quota is None:
        status_info = get_my_quota_status(user_email=resolved_email, tool_context=tool_context)
        if status_info.get("status") == "success":
            current_quota = float(status_info["weekly_limit_usd"])
        else:
            current_quota = 10.0

    base_quota = round(float(current_quota), 2)
    raw_amount = float(requested_quota_usd)
    normalized_duration = normalize_duration(duration_needed)

    # Map option numbers (1, 2, 3) or increments (+15, +25, +50) if raw_amount <= base_quota
    if raw_amount == 1.0:
        target_quota_usd = round(base_quota + 15.0, 2)
    elif raw_amount == 2.0:
        target_quota_usd = round(base_quota + 25.0, 2)
    elif raw_amount == 3.0:
        target_quota_usd = round(base_quota + 50.0, 2)
        if duration_needed == "TEMPORARY_WEEKLY":
            normalized_duration = "PERMANENT"
    elif raw_amount in (15.0, 25.0, 50.0) and raw_amount <= base_quota:
        target_quota_usd = round(base_quota + raw_amount, 2)
    elif raw_amount <= base_quota:
        target_quota_usd = round(base_quota + raw_amount, 2)
    else:
        target_quota_usd = round(raw_amount, 2)

    normalized_category = normalize_reason_category(reason_category)
    clean_justification = (justification or "").strip()
    if len(clean_justification) < 10:
        category_label = REASON_CATEGORY_DESCRIPTIONS.get(normalized_category, normalized_category).split("—")[0].strip()
        if clean_justification:
            clean_justification = f"{category_label}: {clean_justification}"
        else:
            clean_justification = f"Submitted via Antigravity Quota Concierge ({category_label})."

    payload = {
        "requested_quota_usd": target_quota_usd,
        "reason_category": normalized_category,
        "justification": clean_justification,
        "duration_needed": normalized_duration,
        "user_email": resolved_email,
    }

    status_code, resp_data = _portal_http_request(
        method="POST",
        path="/api/quota-requests",
        target_user_email=resolved_email,
        json_body=payload,
    )

    if status_code == 201 and isinstance(resp_data, dict):
        request_id = resp_data.get("request_id", "")
        if tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
            tool_context.state["active_request_id"] = request_id
            tool_context.state["last_submitted_request"] = resp_data
            if raw_amount in (1.0, 2.0, 3.0):
                tool_context.state["user:preferred_option"] = int(raw_amount)
            elif target_quota_usd == round(base_quota + 15.0, 2):
                tool_context.state["user:preferred_option"] = 1
            elif target_quota_usd == round(base_quota + 25.0, 2):
                tool_context.state["user:preferred_option"] = 2
            elif target_quota_usd == round(base_quota + 50.0, 2):
                tool_context.state["user:preferred_option"] = 3
            tool_context.state["user:last_reason_category"] = normalized_category

        duration_label = (
            "Temporary (rest of current week)"
            if normalized_duration == "TEMPORARY_WEEKLY"
            else "Permanent weekly override"
        )
        return {
            "status": "submitted",
            "request_id": request_id,
            "user_email": resolved_email,
            "previous_quota_usd": base_quota,
            "requested_quota_usd": target_quota_usd,
            "duration_needed": normalized_duration,
            "duration_label": duration_label,
            "reason_category": normalized_category,
            "justification": clean_justification,
            "request_status": resp_data.get("status", "PENDING"),
            "confirmation_message": (
                f"Your quota increase request ({request_id}) to raise your weekly limit from "
                f"${base_quota:.2f} to ${target_quota_usd:.2f} ({duration_label}) under "
                f"'{normalized_category}' has been submitted to the Antigravity Quota Portal approval queue. "
                f"An administrator can review and approve it directly in the Quota Increase Requests dashboard. "
                f"As soon as it is approved, your Antigravity access will be automatically restored."
            ),
        }

    detail = resp_data.get("detail") if isinstance(resp_data, dict) else str(resp_data)
    if status_code == 409:
        return {
            "status": "conflict_already_pending",
            "http_status": 409,
            "user_email": resolved_email,
            "error": detail or "A quota increase request is already pending review for your account.",
        }
    if status_code == 429:
        return {
            "status": "cooldown_active",
            "http_status": 429,
            "user_email": resolved_email,
            "error": detail or "Request cooldown is currently active from a prior declined request.",
        }

    return {
        "status": "error",
        "http_status": status_code,
        "user_email": resolved_email,
        "error": f"Failed to submit quota increase request: {detail}",
    }


def cancel_pending_quota_request(
    request_id: str | None = None,
    user_email: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Cancel the employee's pending quota increase request (`DELETE /api/quota-requests/{request_id}`).

    Args:
        request_id: ID of the pending quota request to cancel (e.g., `req-abc12345`).
            If omitted, looks up the active pending request from session state or `/api/auth/me`.
        user_email: Optional email override.
        tool_context: ADK ToolContext injected automatically by the ADK runner.
    """
    resolved_email = resolve_employee_email(tool_context=tool_context, explicit_email=user_email)
    target_req_id = (request_id or "").strip()

    if not target_req_id and tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
        target_req_id = str(tool_context.state.get("active_request_id") or "").strip()

    if not target_req_id:
        status_info = get_my_quota_status(user_email=resolved_email, tool_context=tool_context)
        active_req = status_info.get("active_request") if isinstance(status_info, dict) else None
        if isinstance(active_req, dict):
            target_req_id = str(active_req.get("request_id") or "").strip()

    if not target_req_id:
        return {
            "status": "error",
            "user_email": resolved_email,
            "error": "No pending quota increase request was found to cancel.",
        }

    status_code, resp_data = _portal_http_request(
        method="DELETE",
        path=f"/api/quota-requests/{target_req_id}",
        target_user_email=resolved_email,
    )

    if status_code == 200 and isinstance(resp_data, dict):
        if tool_context is not None and isinstance(getattr(tool_context, "state", None), dict):
            tool_context.state["active_request_id"] = None
        return {
            "status": "cancelled",
            "request_id": target_req_id,
            "user_email": resolved_email,
            "message": f"Pending quota request {target_req_id} has been cancelled. You can now submit a new request.",
        }

    detail = resp_data.get("detail") if isinstance(resp_data, dict) else str(resp_data)
    return {
        "status": "error",
        "http_status": status_code,
        "request_id": target_req_id,
        "user_email": resolved_email,
        "error": f"Could not cancel quota request {target_req_id}: {detail}",
    }
