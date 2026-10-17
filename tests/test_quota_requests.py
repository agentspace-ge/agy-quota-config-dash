"""Unit tests for QuotaRequest models and Database Layer (Mock & Firestore)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.db.mock_db import MockDatabase
from app.db.models import (
    AppConfig,
    CurrentWeekUsage,
    QuotaRequest,
    QuotaRequestBulkReview,
    QuotaRequestCreate,
    QuotaRequestDuration,
    QuotaRequestReasonCategory,
    QuotaRequestReview,
    QuotaRequestStatus,
    User,
    UserStatus,
)


def test_quota_request_enums():
    """Verify all required enum values exist."""
    assert QuotaRequestStatus.PENDING == "PENDING"
    assert QuotaRequestStatus.APPROVED == "APPROVED"
    assert QuotaRequestStatus.REJECTED == "REJECTED"
    assert QuotaRequestStatus.CANCELLED == "CANCELLED"

    assert QuotaRequestDuration.TEMPORARY_WEEKLY == "TEMPORARY_WEEKLY"
    assert QuotaRequestDuration.PERMANENT == "PERMANENT"

    assert QuotaRequestReasonCategory.SPRINT_DEADLINE == "SPRINT_DEADLINE"
    assert QuotaRequestReasonCategory.REFACTORING == "REFACTORING"
    assert QuotaRequestReasonCategory.INCIDENT == "INCIDENT"
    assert QuotaRequestReasonCategory.ROLE_UPGRADE == "ROLE_UPGRADE"
    assert QuotaRequestReasonCategory.OTHER == "OTHER"


def test_quota_request_model_defaults():
    """Verify QuotaRequest model field defaults and validation."""
    req = QuotaRequest(
        request_id="req-test-123",
        user_email="dev@example.com",
        justification="Need higher quota for project milestone.",
    )
    assert req.request_id == "req-test-123"
    assert req.user_email == "dev@example.com"
    assert req.current_group_id == "business-users"
    assert req.current_quota_usd == 10.0
    assert req.current_spend_usd == 0.0
    assert req.requested_quota_usd == 25.0
    assert req.reason_category == QuotaRequestReasonCategory.SPRINT_DEADLINE
    assert req.duration_needed == QuotaRequestDuration.TEMPORARY_WEEKLY
    assert req.status == QuotaRequestStatus.PENDING
    assert isinstance(req.created_at, datetime)
    assert req.reviewed_by is None
    assert req.reviewed_at is None
    assert req.admin_note is None
    assert req.approved_quota_usd is None
    assert req.approved_duration is None
    assert req.cooldown_until is None


def test_quota_request_schemas():
    """Verify request schemas for creation, single review, and bulk review."""
    create_schema = QuotaRequestCreate(
        requested_quota_usd=50.0,
        reason_category=QuotaRequestReasonCategory.INCIDENT,
        justification="Hotfix incident on production cluster",
    )
    assert create_schema.requested_quota_usd == 50.0
    assert create_schema.duration_needed == QuotaRequestDuration.TEMPORARY_WEEKLY

    review_schema = QuotaRequestReview(
        action="approve",
        approved_quota_usd=50.0,
        approved_duration=QuotaRequestDuration.TEMPORARY_WEEKLY,
        admin_note="Approved for incident response",
    )
    assert review_schema.action == "approve"
    assert review_schema.approved_quota_usd == 50.0

    bulk_schema = QuotaRequestBulkReview(
        request_ids=["req-1", "req-2"],
        action="reject",
        admin_note="Peak sprint limit exceeded",
    )
    assert bulk_schema.request_ids == ["req-1", "req-2"]
    assert bulk_schema.action == "reject"


def test_user_model_temporary_quota_field():
    """Verify User model has is_temporary_quota field defaulting to False."""
    from app.db.models import CurrentWeekUsage

    user = User(
        email="developer@example.com",
        current_week=CurrentWeekUsage(week_id="2026-W41"),
    )
    assert user.is_temporary_quota is False
    user.is_temporary_quota = True
    assert user.is_temporary_quota is True


def test_app_config_admin_fields():
    """Verify AppConfig has admin_emails and admin_group_email fields with proper defaults."""
    config = AppConfig()
    assert "admin@example.com" in config.admin_emails
    assert config.admin_group_email == ""


def test_mock_db_seeding_and_infrasec_user():
    """Verify mock DB seeds pending request for infrasec and approved request for alice."""
    db = MockDatabase()

    # Check infrasec user
    infrasec_user = db.get_user("infrasec@example.com")
    assert infrasec_user is not None
    assert infrasec_user.status == UserStatus.AUTO_DISABLED
    assert infrasec_user.current_week.gross_spend_usd == 50.40

    # Check seeded quota requests
    requests = db.list_quota_requests()
    assert len(requests) >= 2

    # Check infrasec pending request
    infrasec_reqs = db.list_quota_requests(user_email="infrasec@example.com")
    assert len(infrasec_reqs) == 1
    req = infrasec_reqs[0]
    assert req.status == QuotaRequestStatus.PENDING
    assert req.requested_quota_usd == 75.00
    assert req.reason_category == QuotaRequestReasonCategory.SPRINT_DEADLINE

    # Check alice approved request
    alice_reqs = db.list_quota_requests(user_email="alice.chen@example.com")
    assert len(alice_reqs) == 1
    assert alice_reqs[0].status == QuotaRequestStatus.APPROVED


def test_mock_db_crud_operations():
    """Verify CRUD operations on MockDatabase for QuotaRequests."""
    db = MockDatabase()

    new_req = QuotaRequest(
        request_id="req-crud-test-1",
        user_email="bob.martin@example.com",
        current_group_id="developers",
        current_quota_usd=10.0,
        current_spend_usd=8.74,
        requested_quota_usd=30.0,
        reason_category=QuotaRequestReasonCategory.REFACTORING,
        justification="Refactoring large module",
        duration_needed=QuotaRequestDuration.TEMPORARY_WEEKLY,
    )

    # 1. Create
    created = db.create_quota_request(new_req)
    assert created.request_id == "req-crud-test-1"
    assert created.status == QuotaRequestStatus.PENDING

    # 2. Get
    fetched = db.get_quota_request("req-crud-test-1")
    assert fetched is not None
    assert fetched.user_email == "bob.martin@example.com"
    assert db.get_quota_request("non-existent-id") is None

    # 3. List with filters
    bob_pending = db.list_quota_requests(
        user_email="bob.martin@example.com",
        status=QuotaRequestStatus.PENDING,
    )
    assert len(bob_pending) == 1
    assert bob_pending[0].request_id == "req-crud-test-1"

    bob_approved = db.list_quota_requests(
        user_email="bob.martin@example.com",
        status=QuotaRequestStatus.APPROVED,
    )
    assert len(bob_approved) == 0

    # 4. Update
    now = datetime.now(UTC)
    updated = db.update_quota_request(
        "req-crud-test-1",
        {
            "status": QuotaRequestStatus.APPROVED,
            "reviewed_by": "admin@example.com",
            "reviewed_at": now,
            "admin_note": "Approved for 1 week refactoring",
            "approved_quota_usd": 30.0,
            "approved_duration": QuotaRequestDuration.TEMPORARY_WEEKLY,
        },
    )
    assert updated is not None
    assert updated.status == QuotaRequestStatus.APPROVED
    assert updated.approved_quota_usd == 30.0
    assert updated.reviewed_by == "admin@example.com"

    # Nonexistent update returns None
    assert db.update_quota_request("non-existent-id", {"status": QuotaRequestStatus.REJECTED}) is None


def test_mock_db_cancel_quota_request():
    """Verify developer self-cancellation rules on MockDatabase."""
    db = MockDatabase()

    req = QuotaRequest(
        request_id="req-cancel-test",
        user_email="charlie.davis@example.com",
        justification="Need temporary boost",
    )
    db.create_quota_request(req)

    # Cancel with wrong email should fail
    wrong_cancel = db.cancel_quota_request("req-cancel-test", user_email="other@example.com")
    assert wrong_cancel is None
    assert db.get_quota_request("req-cancel-test").status == QuotaRequestStatus.PENDING

    # Cancel with correct email should succeed
    cancelled = db.cancel_quota_request("req-cancel-test", user_email="charlie.davis@example.com")
    assert cancelled is not None
    assert cancelled.status == QuotaRequestStatus.CANCELLED

    # Re-cancelling already cancelled request should fail
    re_cancel = db.cancel_quota_request("req-cancel-test", user_email="charlie.davis@example.com")
    assert re_cancel is None


def test_firestore_database_quota_requests_interface():
    """Verify FirestoreDatabase implements quota requests CRUD interface methods."""
    from app.db.firestore_client import FirestoreDatabase

    # Check method existence
    assert hasattr(FirestoreDatabase, "create_quota_request")
    assert hasattr(FirestoreDatabase, "get_quota_request")
    assert hasattr(FirestoreDatabase, "list_quota_requests")
    assert hasattr(FirestoreDatabase, "update_quota_request")
    assert hasattr(FirestoreDatabase, "cancel_quota_request")


def test_evaluator_temporary_quota_reverts_on_weekly_reset(evaluator, mock_db, mock_bq, mock_identity):
    """Verify evaluator reverts temporary quota on pool reset, restoring group quota."""
    old_week = "2026-W01"

    # User with temporary quota of $100.00 in developers group ($50.00 allowance)
    temp_user = User(
        email="temp.dev@example.com",
        group_id="developers",
        status=UserStatus.ACTIVE,
        has_custom_quota=True,
        custom_quota_usd=100.00,
        is_temporary_quota=True,
        current_week=CurrentWeekUsage(
            week_id=old_week,
            total_tokens=1000000,
            gross_spend_usd=2.50,
            quota_credits_usd=100.00,
        ),
    )
    mock_db.save_user(temp_user)

    # User with permanent custom quota of $75.00
    perm_user = User(
        email="perm.dev@example.com",
        group_id="developers",
        status=UserStatus.ACTIVE,
        has_custom_quota=True,
        custom_quota_usd=75.00,
        is_temporary_quota=False,
        current_week=CurrentWeekUsage(
            week_id=old_week,
            total_tokens=1000000,
            gross_spend_usd=2.50,
            quota_credits_usd=75.00,
        ),
    )
    mock_db.save_user(perm_user)

    # Trigger evaluation with weekly reset
    result = evaluator.run_evaluation(triggered_by="test_reset", is_publish=True)
    assert result.success is True

    # Temp user should have temporary quota cleared and reverted to developers group quota ($50.00)
    updated_temp = mock_db.get_user("temp.dev@example.com")
    assert updated_temp.is_temporary_quota is False
    assert updated_temp.has_custom_quota is False
    assert updated_temp.custom_quota_usd is None
    assert updated_temp.current_week.quota_credits_usd == 50.00

    # Permanent user should keep their custom quota ($75.00)
    updated_perm = mock_db.get_user("perm.dev@example.com")
    assert updated_perm.has_custom_quota is True
    assert updated_perm.custom_quota_usd == 75.00
    assert updated_perm.current_week.quota_credits_usd == 75.00


def test_api_auth_me_admin(client):
    """Verify /api/auth/me returns admin profile and status."""
    resp = client.get("/api/auth/me", headers={"X-User-Email": "admin@example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "admin@example.com"
    assert data["is_admin"] is True
    assert data["is_impersonating"] is False
    assert data["user"] is not None


def test_api_auth_me_impersonation_for_admin(client):
    """Verify admin can preview developer view via ?as_user query parameter."""
    resp = client.get(
        "/api/auth/me?as_user=infrasec@example.com",
        headers={"X-User-Email": "admin@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "infrasec@example.com"
    assert data["caller_email"] == "admin@example.com"
    assert data["is_admin"] is True
    assert data["is_impersonating"] is True
    assert data["user"]["status"] == "AUTO_DISABLED"


def test_api_auth_me_jit_provisioning(client, mock_db):
    """Verify unknown authenticated user is automatically provisioned into business-users group."""
    new_email = "newhire@example.com"
    assert mock_db.get_user(new_email) is None

    resp = client.get("/api/auth/me", headers={"X-User-Email": new_email})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == new_email
    assert data["is_admin"] is False
    assert data["user"]["group_id"] == "business-users"
    assert data["user"]["status"] == "ACTIVE"

    # Verify persisted in DB
    user_in_db = mock_db.get_user(new_email)
    assert user_in_db is not None
    assert user_in_db.group_id == "business-users"


def test_api_submit_quota_request_and_anti_spam(client):
    """Verify quota request submission and 409 Conflict anti-spam on duplicate pending."""
    dev_email = "solo.dev@example.com"

    # 1. First submission succeeds
    resp1 = client.post(
        "/api/quota-requests",
        json={
            "requested_quota_usd": 65.0,
            "reason_category": "SPRINT_DEADLINE",
            "justification": "Final sprint release needs more context window",
            "duration_needed": "TEMPORARY_WEEKLY",
        },
        headers={"X-User-Email": dev_email},
    )
    assert resp1.status_code == 201
    req_data = resp1.json()
    assert req_data["user_email"] == dev_email
    assert req_data["requested_quota_usd"] == 65.0
    assert req_data["status"] == "PENDING"

    # 2. Duplicate submission while pending returns 409 Conflict (Anti-Spam)
    resp2 = client.post(
        "/api/quota-requests",
        json={
            "requested_quota_usd": 80.0,
            "reason_category": "INCIDENT",
            "justification": "Another request while first is pending",
        },
        headers={"X-User-Email": dev_email},
    )
    assert resp2.status_code == 409
    assert "already pending" in resp2.json()["detail"]


def test_api_cancel_quota_request(client):
    """Verify developer can self-cancel their pending request."""
    dev_email = "cancelable.dev@example.com"

    # Create request
    create_resp = client.post(
        "/api/quota-requests",
        json={
            "requested_quota_usd": 50.0,
            "reason_category": "REFACTORING",
            "justification": "Refactoring module",
        },
        headers={"X-User-Email": dev_email},
    )
    assert create_resp.status_code == 201
    request_id = create_resp.json()["request_id"]

    # Cancel request as developer
    del_resp = client.delete(f"/api/quota-requests/{request_id}", headers={"X-User-Email": dev_email})
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "CANCELLED"

    # Now developer can submit a fresh request without 409
    fresh_resp = client.post(
        "/api/quota-requests",
        json={
            "requested_quota_usd": 50.0,
            "reason_category": "REFACTORING",
            "justification": "Fresh submission after cancellation",
        },
        headers={"X-User-Email": dev_email},
    )
    assert fresh_resp.status_code == 201


def test_api_review_quota_request_approval_flexibility(client, mock_db):
    """Verify OpenAI Approval Flexibility: custom amount, temporary duration, and unthrottling."""
    target_user = "infrasec@example.com"

    # User is currently AUTO_DISABLED in seeded mock_db
    user_before = mock_db.get_user(target_user)
    assert user_before.status.value == "AUTO_DISABLED"

    # Seeded pending request id is 'req-seed-infrasec'
    review_resp = client.patch(
        "/api/quota-requests/req-seed-infrasec",
        json={
            "action": "approve",
            "approved_quota_usd": 80.00,
            "approved_duration": "TEMPORARY_WEEKLY",
            "admin_note": "Approved temporary sprint boost for Q4 delivery",
        },
        headers={"X-User-Email": "admin@example.com"},
    )
    assert review_resp.status_code == 200
    reviewed_data = review_resp.json()
    assert reviewed_data["status"] == "APPROVED"
    assert reviewed_data["approved_quota_usd"] == 80.00
    assert reviewed_data["approved_duration"] == "TEMPORARY_WEEKLY"

    # Verify user record was updated and unthrottled
    user_after = mock_db.get_user(target_user)
    assert user_after.has_custom_quota is True
    assert user_after.custom_quota_usd == 80.00
    assert user_after.is_temporary_quota is True
    # User had spend $50.40, quota is now $80.00, so status should be restored to ACTIVE!
    assert user_after.status.value == "ACTIVE"


def test_api_review_quota_request_rejection_and_cooldown(client, mock_db):
    """Verify rejection sets admin note and enforces cooldown on subsequent submissions."""
    dev_email = "declined.dev@example.com"

    # Submit request
    create_resp = client.post(
        "/api/quota-requests",
        json={
            "requested_quota_usd": 150.0,
            "reason_category": "OTHER",
            "justification": "Need massive quota",
        },
        headers={"X-User-Email": dev_email},
    )
    assert create_resp.status_code == 201
    req_id = create_resp.json()["request_id"]

    # Reject as admin
    rej_resp = client.patch(
        f"/api/quota-requests/{req_id}",
        json={
            "action": "reject",
            "admin_note": "Quota exceedance not justified for this tier",
        },
        headers={"X-User-Email": "admin@example.com"},
    )
    assert rej_resp.status_code == 200
    assert rej_resp.json()["status"] == "REJECTED"
    assert rej_resp.json()["cooldown_until"] is not None

    # Immediate re-submission by dev returns 429 Too Many Requests (Cooldown active)
    retry_resp = client.post(
        "/api/quota-requests",
        json={
            "requested_quota_usd": 100.0,
            "reason_category": "OTHER",
            "justification": "Trying again",
        },
        headers={"X-User-Email": dev_email},
    )
    assert retry_resp.status_code == 429
    assert "Request cooldown active" in retry_resp.json()["detail"]


def test_api_bulk_review_quota_requests(client):
    """Verify batch approval of multiple requests."""
    emails = ["bulk1@example.com", "bulk2@example.com"]
    req_ids = []
    for email in emails:
        r = client.post(
            "/api/quota-requests",
            json={
                "requested_quota_usd": 40.0,
                "reason_category": "SPRINT_DEADLINE",
                "justification": "Bulk test sprint",
            },
            headers={"X-User-Email": email},
        )
        req_ids.append(r.json()["request_id"])

    bulk_resp = client.post(
        "/api/quota-requests/bulk-review",
        json={
            "request_ids": req_ids,
            "action": "approve",
            "approved_duration": "TEMPORARY_WEEKLY",
            "admin_note": "Bulk sprint approval",
        },
        headers={"X-User-Email": "admin@example.com"},
    )
    assert bulk_resp.status_code == 200
    assert bulk_resp.json()["updated_count"] == 2

