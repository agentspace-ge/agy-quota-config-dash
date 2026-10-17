"""REST API endpoints for Quota Requests lifecycle, review, and governance."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    get_current_user_context,
    get_db,
    get_identity,
    get_pool_client,
    require_admin,
)
from app.db.models import (
    AuditEvent,
    QuotaRequest,
    QuotaRequestBulkReview,
    QuotaRequestCreate,
    QuotaRequestDuration,
    QuotaRequestReview,
    QuotaRequestStatus,
    UserStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quota-requests", tags=["Quota Requests"])


@router.post("", response_model=QuotaRequest, status_code=status.HTTP_201_CREATED)
def submit_quota_request(
    payload: QuotaRequestCreate,
    context: dict[str, Any] = Depends(get_current_user_context),
    db: Any = Depends(get_db),
    pool_client: Any = Depends(get_pool_client),
):
    """Submit a new quota increase request.

    Enforces anti-spam checks: returns 409 Conflict if pending request exists,
    and 429 Too Many Requests if currently in cooldown from a prior rejection.
    """
    user_email = context["effective_email"]
    if payload.user_email and (
        context.get("is_admin")
        or context.get("is_trusted_service_account")
        or context.get("is_impersonating")
    ):
        user_email = payload.user_email.strip().lower()
    now = datetime.now(UTC)

    # 1. Check existing requests for anti-spam / cooldown
    existing_requests = db.list_quota_requests(user_email=user_email)
    for req in existing_requests:
        if req.status == QuotaRequestStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A quota increase request is already pending review for your account.",
            )

    rejected_requests = [r for r in existing_requests if r.status == QuotaRequestStatus.REJECTED and r.cooldown_until]
    if rejected_requests:
        latest_rejected = max(rejected_requests, key=lambda r: r.reviewed_at or r.created_at)
        if latest_rejected.cooldown_until and latest_rejected.cooldown_until > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Request cooldown active until {latest_rejected.cooldown_until.isoformat()}. "
                    f"Admin note: {latest_rejected.admin_note or 'No reason provided'}"
                ),
            )

    # 2. Get user profile for baseline metrics
    user = db.get_user(user_email)
    current_group_id = user.group_id if user else "business-users"
    current_quota = 10.0
    current_spend = 0.0

    if user and user.current_week:
        current_quota = user.current_week.quota_credits_usd
        current_spend = user.current_week.gross_spend_usd

    # 3. Create request
    request_id = f"req-{uuid.uuid4().hex[:10]}"
    quota_req = QuotaRequest(
        request_id=request_id,
        user_email=user_email,
        current_group_id=current_group_id,
        current_quota_usd=current_quota,
        current_spend_usd=current_spend,
        requested_quota_usd=payload.requested_quota_usd,
        reason_category=payload.reason_category,
        justification=payload.justification,
        duration_needed=payload.duration_needed,
        status=QuotaRequestStatus.PENDING,
        created_at=now,
    )

    created = db.create_quota_request(quota_req)

    db.add_audit_event(
        AuditEvent(
            event_id=f"evt-req-sub-{uuid.uuid4().hex[:8]}",
            timestamp=now,
            action="QUOTA_REQUEST_SUBMITTED",
            triggered_by=user_email,
            target_user=user_email,
            details={
                "request_id": request_id,
                "requested_quota_usd": payload.requested_quota_usd,
                "reason_category": payload.reason_category.value,
                "duration_needed": payload.duration_needed.value,
            },
        )
    )

    return created


@router.get("", response_model=list[QuotaRequest])
def list_quota_requests(
    user_email: str | None = Query(None, description="Filter by user email"),
    status_filter: QuotaRequestStatus | None = Query(None, alias="status", description="Filter by status"),
    context: dict[str, Any] = Depends(get_current_user_context),
    db: Any = Depends(get_db),
):
    """List quota requests with role-based scoping and filtering."""
    if not context["is_admin"]:
        # Standard developer can only view their own requests
        user_email = context["caller_email"]

    return db.list_quota_requests(user_email=user_email, status=status_filter)


@router.delete("/{request_id}", response_model=QuotaRequest)
def cancel_quota_request(
    request_id: str,
    context: dict[str, Any] = Depends(get_current_user_context),
    db: Any = Depends(get_db),
):
    """Developer self-service cancellation of their own pending quota request."""
    user_email = context["effective_email"]
    cancelled = db.cancel_quota_request(request_id=request_id, user_email=user_email)

    if cancelled is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel request: request not found, already reviewed, or does not belong to you.",
        )

    db.add_audit_event(
        AuditEvent(
            event_id=f"evt-req-can-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(UTC),
            action="QUOTA_REQUEST_CANCELLED",
            triggered_by=user_email,
            target_user=user_email,
            details={"request_id": request_id},
        )
    )

    return cancelled


@router.patch("/{request_id}", response_model=QuotaRequest)
def review_quota_request(
    request_id: str,
    payload: QuotaRequestReview,
    admin_context: dict[str, Any] = Depends(require_admin),
    db: Any = Depends(get_db),
    identity: Any = Depends(get_identity),
    pool_client: Any = Depends(get_pool_client),
):
    """Administrative review endpoint supporting OpenAI-style Approval Flexibility and Claude Cooldown."""
    reviewer_email = admin_context["caller_email"]
    now = datetime.now(UTC)

    req = db.get_quota_request(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quota request not found")

    if req.status != QuotaRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is already in '{req.status.value}' state and cannot be modified.",
        )

    action = payload.action.lower().strip()

    if action == "approve":
        approved_quota = (
            payload.approved_quota_usd if payload.approved_quota_usd is not None else req.requested_quota_usd
        )
        approved_duration = (
            payload.approved_duration if payload.approved_duration is not None else req.duration_needed
        )

        updates = {
            "status": QuotaRequestStatus.APPROVED,
            "reviewed_by": reviewer_email,
            "reviewed_at": now,
            "approved_quota_usd": approved_quota,
            "approved_duration": approved_duration,
            "admin_note": payload.admin_note,
        }
        updated_req = db.update_quota_request(request_id, updates)

        # Apply quota update directly to the user record
        user = db.get_user(req.user_email)
        if user:
            user.has_custom_quota = True
            user.custom_quota_usd = approved_quota
            user.is_temporary_quota = approved_duration == QuotaRequestDuration.TEMPORARY_WEEKLY
            user.updated_at = now

            if user.current_week:
                user.current_week.quota_credits_usd = approved_quota
                buffer = user.current_week.overage_buffer_usd
                user.current_week.remaining_credit_usd = max(0.0, approved_quota - user.current_week.gross_spend_usd)

                # Re-enable if user was throttled and new quota covers their current spend
                if user.status == UserStatus.AUTO_DISABLED:
                    if user.current_week.gross_spend_usd <= (approved_quota + buffer):
                        user.status = UserStatus.ACTIVE
                        identity.add_member_to_group(identity.enabled_group_email, user.email)
                        identity.remove_member_from_group(identity.disabled_group_email, user.email)

            db.save_user(user)

        db.add_audit_event(
            AuditEvent(
                event_id=f"evt-req-app-{uuid.uuid4().hex[:8]}",
                timestamp=now,
                action="QUOTA_REQUEST_APPROVED",
                triggered_by=reviewer_email,
                target_user=req.user_email,
                details={
                    "request_id": request_id,
                    "approved_quota_usd": approved_quota,
                    "approved_duration": approved_duration.value,
                    "admin_note": payload.admin_note,
                },
            )
        )
        return updated_req

    elif action == "reject":
        # Calculate cooldown timestamp: until upcoming pool reset or next Monday
        cooldown_target = now + timedelta(days=7)
        try:
            pool_stats = pool_client.get_pool_stats(force_refresh=False)
            if pool_stats and pool_stats.next_reset_utc:
                cooldown_target = pool_stats.next_reset_utc
        except Exception:
            pass

        updates = {
            "status": QuotaRequestStatus.REJECTED,
            "reviewed_by": reviewer_email,
            "reviewed_at": now,
            "admin_note": payload.admin_note or "Declined by administrator",
            "cooldown_until": cooldown_target,
        }
        updated_req = db.update_quota_request(request_id, updates)

        db.add_audit_event(
            AuditEvent(
                event_id=f"evt-req-rej-{uuid.uuid4().hex[:8]}",
                timestamp=now,
                action="QUOTA_REQUEST_REJECTED",
                triggered_by=reviewer_email,
                target_user=req.user_email,
                details={
                    "request_id": request_id,
                    "admin_note": payload.admin_note,
                    "cooldown_until": cooldown_target.isoformat(),
                },
            )
        )
        return updated_req

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid review action '{payload.action}'. Expected 'approve' or 'reject'.",
        )


@router.post("/bulk-review")
def bulk_review_quota_requests(
    payload: QuotaRequestBulkReview,
    admin_context: dict[str, Any] = Depends(require_admin),
    db: Any = Depends(get_db),
    identity: Any = Depends(get_identity),
    pool_client: Any = Depends(get_pool_client),
):
    """Batch approve or reject multiple quota requests in one administrative action."""
    action_payload = QuotaRequestReview(
        action=payload.action,
        approved_quota_usd=payload.approved_quota_usd,
        approved_duration=payload.approved_duration,
        admin_note=payload.admin_note,
    )

    success_count = 0
    for req_id in payload.request_ids:
        try:
            review_quota_request(
                request_id=req_id,
                payload=action_payload,
                admin_context=admin_context,
                db=db,
                identity=identity,
                pool_client=pool_client,
            )
            success_count += 1
        except Exception as e:
            logger.warning(f"Bulk review skipped {req_id}: {e}")

    return {"updated_count": success_count, "total_requested": len(payload.request_ids)}
