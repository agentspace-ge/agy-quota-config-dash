"""Authentication, identity resolution, and developer self-service profile endpoint."""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_context, get_db, get_pool_client
from app.db.models import (
    CurrentWeekUsage,
    QuotaGroup,
    QuotaRequest,
    QuotaRequestStatus,
    User,
    UserStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.get("/me")
def get_auth_me(
    context: dict[str, Any] = Depends(get_current_user_context),
    db: Any = Depends(get_db),
    pool_client: Any = Depends(get_pool_client),
):
    """Return the authenticated caller identity, permissions, quota status, and active requests.

    Supports testing developer view for admins via ?as_user=<email> or X-Impersonate-User.
    Automatically provisions unknown authenticated users into default 'business-users' group.
    """
    caller_email = context["caller_email"]
    effective_email = context["effective_email"]
    is_admin = context["is_admin"]
    is_impersonating = context["is_impersonating"]

    now = datetime.now(UTC)

    # 1. Fetch or JIT-provision user
    user = db.get_user(effective_email)
    if user is None:
        logger.info(f"Just-in-Time provisioning new user '{effective_email}' into 'business-users' group")
        default_group = db.get_group("business-users")
        default_quota = default_group.weekly_quota_usd if default_group else 10.00
        default_overage = default_group.overage_buffer_usd if default_group else 2.00

        user = User(
            email=effective_email,
            group_id="business-users",
            status=UserStatus.ACTIVE,
            is_exempt=False,
            has_custom_quota=False,
            custom_quota_usd=None,
            custom_overage_usd=None,
            is_temporary_quota=False,
            current_week=CurrentWeekUsage(
                week_id=now.strftime("%Y-W%W"),
                window_start_utc=now,
                total_tokens=0,
                total_requests=0,
                gross_spend_usd=0.00,
                quota_credits_usd=default_quota,
                remaining_credit_usd=default_quota,
                net_billable_cost_usd=0.00,
                overage_buffer_usd=default_overage,
                credit_utilization_percentage=0.0,
            ),
            created_at=now,
            updated_at=now,
        )
        db.save_user(user)

    # 2. Fetch assigned group
    group = db.get_group(user.group_id) if user.group_id else None

    # 3. Fetch credit pool stats for reset countdown
    credit_pool = None
    try:
        credit_pool = pool_client.get_pool_stats(force_refresh=False)
    except Exception as e:
        logger.warning(f"Could not retrieve credit pool stats for /me: {e}")

    # 4. Check active quota request & cooldown status
    user_requests = db.list_quota_requests(user_email=effective_email)

    active_request: QuotaRequest | None = None
    in_cooldown = False
    cooldown_until: datetime | None = None
    admin_note: str | None = None

    for req in user_requests:
        if req.status == QuotaRequestStatus.PENDING:
            active_request = req
            break

    if active_request is None:
        # Check if rejected and cooldown is still active
        rejected_requests = [
            r for r in user_requests if r.status == QuotaRequestStatus.REJECTED and r.cooldown_until is not None
        ]
        if rejected_requests:
            # Get latest rejected request
            latest_rejected = max(rejected_requests, key=lambda r: r.reviewed_at or r.created_at)
            if latest_rejected.cooldown_until and latest_rejected.cooldown_until > now:
                in_cooldown = True
                cooldown_until = latest_rejected.cooldown_until
                admin_note = latest_rejected.admin_note

    # 5. Warning threshold (80%+ spend)
    warning_threshold_reached = False
    if user.status == UserStatus.ACTIVE and user.current_week:
        if user.current_week.credit_utilization_percentage >= 80.0:
            warning_threshold_reached = True

    return {
        "email": effective_email,
        "caller_email": caller_email,
        "is_admin": is_admin,
        "is_impersonating": is_impersonating,
        "user": user,
        "group": group,
        "credit_pool": credit_pool,
        "active_request": active_request,
        "in_cooldown": in_cooldown,
        "cooldown_until": cooldown_until,
        "admin_note": admin_note,
        "warning_threshold_reached": warning_threshold_reached,
    }
