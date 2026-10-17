#!/usr/bin/env python3
"""Run Antigravity Quota Portal locally with 3 demo users and mock usage."""

import os
from datetime import UTC, datetime, timedelta

# Ensure mock services mode is forced
os.environ["USE_MOCK_SERVICES"] = "true"

import uvicorn

from app.api.deps import get_bq, get_db, get_identity, get_pool_client
from app.bq.bq_client import UserUsageRecord
from app.core.timezone_engine import get_current_week_window, resolve_pool_window
from app.db.models import (
    AuditEvent,
    CurrentWeekUsage,
    QuotaRequest,
    QuotaRequestDuration,
    QuotaRequestReasonCategory,
    QuotaRequestStatus,
    SpendBreakdown,
    User,
    UserStatus,
)
from app.main import app


def seed_three_demo_users():
    """Seed exactly 3 users demonstrating each quota state."""
    db = get_db()
    bq = get_bq()
    identity = get_identity()
    pool_client = get_pool_client()

    # Clear existing state
    with db._lock:
        db._users.clear()
        db._audit_events.clear()

    now = datetime.now(UTC)
    config = db.get_config()
    stats = pool_client.get_pool_stats(force_refresh=True)
    week_id, window_start_utc, next_reset_utc, _ = resolve_pool_window(stats, config.timezone, now)
    db.save_credit_pool(stats)

    # 1. Alice - Active, healthy consumption ($4.20 / $10.00)
    user_alice = User(
        email="alice.chen@example.com",
        status=UserStatus.ACTIVE,
        is_exempt=False,
        has_custom_quota=False,
        current_week=CurrentWeekUsage(
            week_id=week_id,
            window_start_utc=window_start_utc,
            total_tokens=2500000,
            total_requests=180,
            gross_spend_usd=4.20,
            quota_credits_usd=10.00,
            remaining_credit_usd=5.80,
            net_billable_cost_usd=0.00,
            overage_buffer_usd=2.00,
            spend_breakdown=SpendBreakdown(
                input_spend_usd=2.80,
                output_spend_usd=1.20,
                cached_spend_usd=0.20,
            ),
            tokens_by_model={"gemini-3-pro": 1500000, "gemini-3.6-flash": 1000000},
            spend_by_model={"gemini-3-pro": 3.75, "gemini-3.6-flash": 0.45},
            credit_utilization_percentage=42.0,
            last_active=now - timedelta(minutes=12),
        ),
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(minutes=12),
    )

    # 2. Bob - Active, warning threshold ($8.50 / $10.00, 85% util)
    user_bob = User(
        email="bob.martin@example.com",
        status=UserStatus.ACTIVE,
        is_exempt=False,
        has_custom_quota=False,
        current_week=CurrentWeekUsage(
            week_id=week_id,
            window_start_utc=window_start_utc,
            total_tokens=4200000,
            total_requests=290,
            gross_spend_usd=8.50,
            quota_credits_usd=10.00,
            remaining_credit_usd=1.50,
            net_billable_cost_usd=0.00,
            overage_buffer_usd=2.00,
            spend_breakdown=SpendBreakdown(
                input_spend_usd=5.80,
                output_spend_usd=2.30,
                cached_spend_usd=0.40,
            ),
            tokens_by_model={"gemini-3-pro": 3500000, "gemini-3.6-flash": 700000},
            spend_by_model={"gemini-3-pro": 8.05, "gemini-3.6-flash": 0.45},
            credit_utilization_percentage=85.0,
            last_active=now - timedelta(minutes=3),
        ),
        created_at=now - timedelta(days=20),
        updated_at=now - timedelta(minutes=3),
    )

    # 3. Charlie - Auto-throttled ($13.40 / $10.00 + $2.00 buffer breached)
    user_charlie = User(
        email="charlie.davis@example.com",
        status=UserStatus.AUTO_DISABLED,
        is_exempt=False,
        has_custom_quota=False,
        current_week=CurrentWeekUsage(
            week_id=week_id,
            window_start_utc=window_start_utc,
            total_tokens=6800000,
            total_requests=520,
            gross_spend_usd=13.40,
            quota_credits_usd=10.00,
            remaining_credit_usd=0.00,
            net_billable_cost_usd=3.40,
            overage_buffer_usd=2.00,
            spend_breakdown=SpendBreakdown(
                input_spend_usd=9.20,
                output_spend_usd=3.60,
                cached_spend_usd=0.60,
            ),
            tokens_by_model={"gemini-3-pro": 5800000, "gemini-2.5-pro": 1000000},
            spend_by_model={"gemini-3-pro": 11.50, "gemini-2.5-pro": 1.90},
            credit_utilization_percentage=134.0,
            last_active=now - timedelta(hours=1),
        ),
        created_at=now - timedelta(days=15),
        updated_at=now - timedelta(hours=1),
    )

    # 4. Infrasec - Auto-throttled developer with pending quota request
    user_infrasec = User(
        email="infrasec@example.com",
        status=UserStatus.AUTO_DISABLED,
        group_id="developers",
        is_exempt=False,
        has_custom_quota=False,
        current_week=CurrentWeekUsage(
            week_id=week_id,
            window_start_utc=window_start_utc,
            total_tokens=18200000,
            total_requests=940,
            gross_spend_usd=50.40,
            quota_credits_usd=50.00,
            remaining_credit_usd=0.00,
            net_billable_cost_usd=0.40,
            overage_buffer_usd=10.00,
            spend_breakdown=SpendBreakdown(
                input_spend_usd=34.00,
                output_spend_usd=14.00,
                cached_spend_usd=2.40,
            ),
            tokens_by_model={"gemini-3-pro": 14000000, "gemini-3.6-flash": 4200000},
            spend_by_model={"gemini-3-pro": 45.50, "gemini-3.6-flash": 4.90},
            credit_utilization_percentage=100.8,
            last_active=now - timedelta(minutes=5),
        ),
        created_at=now - timedelta(days=45),
        updated_at=now - timedelta(minutes=5),
    )

    # Save users
    db.save_user(user_alice)
    db.save_user(user_bob)
    db.save_user(user_charlie)
    db.save_user(user_infrasec)

    # Reconcile mock Cloud Identity group memberships
    identity.reconcile_user_group(user_alice.email, "ENABLED")
    identity.reconcile_user_group(user_bob.email, "ENABLED")
    identity.reconcile_user_group(user_charlie.email, "DISABLED")
    identity.reconcile_user_group(user_infrasec.email, "DISABLED")

    # Seed Quota Requests
    req_pending = QuotaRequest(
        request_id="req-seed-infrasec",
        user_email="infrasec@example.com",
        current_group_id="developers",
        current_quota_usd=50.0,
        current_spend_usd=50.40,
        requested_quota_usd=75.0,
        reason_category=QuotaRequestReasonCategory.SPRINT_DEADLINE,
        justification="Release sprint: running large-scale agentic refactoring and automated integration tests across microservices.",
        duration_needed=QuotaRequestDuration.TEMPORARY_WEEKLY,
        status=QuotaRequestStatus.PENDING,
        created_at=now - timedelta(minutes=25),
    )
    db.create_quota_request(req_pending)

    # Configure mock BigQuery so Publish & Sync preserves these 3 users
    bq.set_custom_records(
        [
            UserUsageRecord(
                user_email="alice.chen@example.com",
                model_name="gemini-3-pro",
                request_count=100,
                token_count=1500000,
                last_active=now - timedelta(minutes=12),
            ),
            UserUsageRecord(
                user_email="alice.chen@example.com",
                model_name="gemini-3.6-flash",
                request_count=80,
                token_count=1000000,
                last_active=now - timedelta(minutes=12),
            ),
            UserUsageRecord(
                user_email="bob.martin@example.com",
                model_name="gemini-3-pro",
                request_count=210,
                token_count=3500000,
                last_active=now - timedelta(minutes=3),
            ),
            UserUsageRecord(
                user_email="bob.martin@example.com",
                model_name="gemini-3.6-flash",
                request_count=80,
                token_count=700000,
                last_active=now - timedelta(minutes=3),
            ),
            UserUsageRecord(
                user_email="charlie.davis@example.com",
                model_name="gemini-3-pro",
                request_count=380,
                token_count=5800000,
                last_active=now - timedelta(hours=1),
            ),
            UserUsageRecord(
                user_email="charlie.davis@example.com",
                model_name="gemini-2.5-pro",
                request_count=140,
                token_count=1000000,
                last_active=now - timedelta(hours=1),
            ),
        ]
    )

    # Seed initial audit events for demo audit trail viewer
    db.add_audit_event(
        AuditEvent(
            event_id="evt-seed-demo-1",
            timestamp=now - timedelta(hours=2, minutes=15),
            action="QUOTA_UPDATE",
            triggered_by="admin_ui",
            target_user="bob.martin@example.com",
            details={
                "custom_quota_usd": 15.00,
                "custom_overage_usd": 3.00,
                "reason": "Admin increased weekly credit quota to $15.00",
            },
        )
    )
    db.add_audit_event(
        AuditEvent(
            event_id="evt-seed-demo-2",
            timestamp=now - timedelta(hours=1, minutes=4),
            action="GROUP_SWAP",
            triggered_by="HOURLY_APS_CRON",
            target_user="charlie.davis@example.com",
            details={
                "direction": "DISABLED",
                "from_group": "antigravity-enabled@example.com",
                "to_group": "antigravity-disabled@example.com",
                "current_spend_usd": 13.40,
                "quota_usd": 10.00,
                "overage_limit_usd": 2.00,
                "reason": "HARD_LIMIT_BREACHED: Spend $13.40 >= Limit $12.00 ($10 quota + $2 buffer)",
            },
        )
    )
    db.add_audit_event(
        AuditEvent(
            event_id="evt-seed-demo-3",
            timestamp=now - timedelta(minutes=22),
            action="PUBLISH_TRIGGERED",
            triggered_by="admin_publish_button",
            target_user=None,
            details={
                "users_evaluated": 3,
                "group_swaps": 1,
                "status": "SUCCESS",
            },
        )
    )


def seed_concierge_demo_user(email: str = "alex.morgan@example.com") -> User:
    """Seed the enterprise Concierge demo persona paused at $6.04 weekly usage vs $6.00 limit."""
    db = get_db()
    identity = get_identity()
    pool_client = get_pool_client()

    now = datetime.now(UTC)
    config = db.get_config()
    stats = pool_client.get_pool_stats(force_refresh=False)
    week_id, window_start_utc, _, _ = resolve_pool_window(stats, config.timezone, now)

    demo_user = User(
        email=email.strip().lower(),
        group_id="business-users",
        status=UserStatus.AUTO_DISABLED,
        is_exempt=False,
        has_custom_quota=True,
        custom_quota_usd=6.00,
        custom_overage_usd=0.00,
        current_week=CurrentWeekUsage(
            week_id=week_id,
            window_start_utc=window_start_utc,
            total_tokens=2950000,
            total_requests=215,
            gross_spend_usd=6.04,
            quota_credits_usd=6.00,
            remaining_credit_usd=0.00,
            net_billable_cost_usd=0.04,
            overage_buffer_usd=0.00,
            spend_breakdown=SpendBreakdown(
                input_spend_usd=4.10,
                output_spend_usd=1.64,
                cached_spend_usd=0.30,
            ),
            tokens_by_model={"gemini-3-pro": 2200000, "gemini-3.5-flash": 750000},
            spend_by_model={"gemini-3-pro": 5.60, "gemini-3.5-flash": 0.44},
            credit_utilization_percentage=100.67,
            last_active=now - timedelta(minutes=8),
        ),
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(minutes=8),
    )
    db.save_user(demo_user)
    identity.reconcile_user_group(demo_user.email, "DISABLED")
    return demo_user


def main():
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")

    seed_three_demo_users()
    if os.environ.get("SEED_CONCIERGE_DEMO_USER", "false").lower() in ("true", "1", "yes"):
        seed_concierge_demo_user()

    print("\n" + "=" * 72)
    print("  🚀 Antigravity Quota Portal - Local Sandbox (3 Demo Users)")
    print("=" * 72)
    print(f"  Portal Dashboard:  http://localhost:{port}")
    print(f"  Interactive API:   http://localhost:{port}/docs")
    print(f"  Health Endpoint:   http://localhost:{port}/api/health")
    print("-" * 72)
    print("  Seeded 3 Demo Users:")
    print("   1. alice.chen@example.com    - ACTIVE        (Spend $4.20 / $10.00,  42% util - Normal)")
    print("   2. bob.martin@example.com    - ACTIVE        (Spend $8.50 / $10.00,  85% util - Warning)")
    print("   3. charlie.davis@example.com - AUTO_DISABLED (Spend $13.40 / $10.00, 134% util - Throttled)")
    print("=" * 72 + "\n")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
