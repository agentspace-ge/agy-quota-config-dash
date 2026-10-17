"""Quota Group management API endpoints."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_db, get_identity
from app.db.models import (
    AuditEvent,
    QuotaGroup,
    QuotaGroupCreateRequest,
    QuotaGroupMembersRequest,
    QuotaGroupUpdateRequest,
    UserStatus,
)

router = APIRouter(prefix="/api/groups", tags=["Groups"])


@router.get("", response_model=list[QuotaGroup])
def list_groups(db=Depends(get_db)):
    """List all quota groups with member counts, gross spend, and token statistics."""
    if hasattr(db, "list_groups"):
        return db.list_groups()
    return []


@router.post("", response_model=QuotaGroup, status_code=201)
def create_group(
    payload: QuotaGroupCreateRequest,
    db=Depends(get_db),
):
    """Create a new quota group."""
    key = payload.group_id.strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="Group ID cannot be empty")

    existing = db.get_group(key)
    if existing:
        raise HTTPException(status_code=400, detail=f"Group '{key}' already exists")

    now = datetime.now(UTC)
    new_group = QuotaGroup(
        group_id=key,
        display_name=payload.display_name.strip() or key.capitalize(),
        description=payload.description.strip(),
        weekly_quota_usd=payload.weekly_quota_usd,
        overage_buffer_usd=payload.overage_buffer_usd,
        is_exempt=payload.is_exempt,
        iam_group_email=payload.iam_group_email,
        created_at=now,
        updated_at=now,
    )

    created = db.create_group(new_group)

    db.add_audit_event(
        AuditEvent(
            event_id=f"evt-grp-create-{uuid.uuid4().hex[:8]}",
            timestamp=now,
            action="GROUP_CREATED",
            triggered_by="admin_ui",
            target_user=None,
            details=created.model_dump(mode="json"),
        )
    )

    return created


@router.get("/{group_id}", response_model=QuotaGroup)
def get_group(group_id: str, db=Depends(get_db)):
    """Get details and live metrics for a specific quota group."""
    group = db.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    return group


@router.put("/{group_id}", response_model=QuotaGroup)
def update_group(
    group_id: str,
    payload: QuotaGroupUpdateRequest,
    db=Depends(get_db),
    identity=Depends(get_identity),
):
    """Update quota limits, display metadata, or exemption status for a quota group."""
    key = group_id.strip().lower()
    group = db.get_group(key)
    if not group:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return group

    updated_group = db.update_group(key, updates)

    # Propagate updated quotas to members without custom quotas
    now = datetime.now(UTC)
    all_users = db.list_users()
    recalculated_users = []
    for user in all_users:
        if user.group_id == key:
            changed = False
            if not user.has_custom_quota:
                if "weekly_quota_usd" in updates and updates["weekly_quota_usd"] is not None:
                    user.current_week.quota_credits_usd = updates["weekly_quota_usd"]
                    user.current_week.remaining_credit_usd = max(
                        0.0, round(updates["weekly_quota_usd"] - user.current_week.gross_spend_usd, 2)
                    )
                    changed = True
                if "overage_buffer_usd" in updates and updates["overage_buffer_usd"] is not None:
                    user.current_week.overage_buffer_usd = updates["overage_buffer_usd"]
                    changed = True

            # If group became exempt, restore auto-disabled members
            if updates.get("is_exempt") is True and user.status == UserStatus.AUTO_DISABLED:
                user.status = UserStatus.ACTIVE
                identity.reconcile_user_group(user.email, "ENABLED")
                changed = True

            if changed:
                user.updated_at = now
                recalculated_users.append(user)

    if recalculated_users:
        db.save_users(recalculated_users)

    db.add_audit_event(
        AuditEvent(
            event_id=f"evt-grp-update-{uuid.uuid4().hex[:8]}",
            timestamp=now,
            action="GROUP_UPDATED",
            triggered_by="admin_ui",
            target_user=None,
            details={"group_id": key, "updates": updates, "members_recalculated": len(recalculated_users)},
        )
    )

    return updated_group or group


@router.delete("/{group_id}")
def delete_group(group_id: str, db=Depends(get_db)):
    """Delete a quota group and reassign all of its members to the default 'business-users' group."""
    key = group_id.strip().lower()
    if key == "business-users":
        raise HTTPException(status_code=400, detail="Cannot delete default 'business-users' group")

    group = db.get_group(key)
    if not group:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")

    success = db.delete_group(key)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to delete group '{group_id}'")

    now = datetime.now(UTC)
    db.add_audit_event(
        AuditEvent(
            event_id=f"evt-grp-del-{uuid.uuid4().hex[:8]}",
            timestamp=now,
            action="GROUP_DELETED",
            triggered_by="admin_ui",
            target_user=None,
            details={"deleted_group": key, "reassigned_to": "business-users"},
        )
    )

    return {"deleted": True, "group_id": key, "reassigned_to": "business-users"}


@router.post("/{group_id}/members")
def assign_group_members(
    group_id: str,
    payload: QuotaGroupMembersRequest,
    db=Depends(get_db),
):
    """Bulk assign or reassign users to a quota group by a list of email addresses."""
    key = group_id.strip().lower()
    group = db.get_group(key)
    if not group:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")

    action = payload.action.strip().lower()
    clean_emails = [e.strip().lower() for e in payload.emails if e.strip()]

    if action == "replace":
        # Reassign all existing members to business-users first
        all_users = db.list_users()
        reassigned = []
        now = datetime.now(UTC)
        for user in all_users:
            if user.group_id == key and user.email.lower() not in clean_emails:
                user.group_id = "business-users"
                user.updated_at = now
                reassigned.append(user)
        if reassigned:
            db.save_users(reassigned)

    count = db.bulk_assign_group_members(
        key, clean_emails, reset_custom_quota=payload.reset_custom_quota
    )

    now = datetime.now(UTC)
    db.add_audit_event(
        AuditEvent(
            event_id=f"evt-grp-members-{uuid.uuid4().hex[:8]}",
            timestamp=now,
            action="GROUP_MEMBERS_ASSIGNED",
            triggered_by="admin_ui",
            target_user=None,
            details={
                "group_id": key,
                "action": action,
                "assigned_count": count,
                "reset_custom_quota": payload.reset_custom_quota,
            },
        )
    )

    return {"success": True, "group_id": key, "assigned_count": count}
