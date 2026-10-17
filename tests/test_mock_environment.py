"""Tests for mockup environment initialization, mock services, and demo seeding."""

from datetime import UTC, datetime, timedelta

from app.api.deps import get_db, get_identity, get_pool_client
from app.bq.mock_bq import MockBigQueryUsageClient
from app.core.evaluator import QuotaEvaluator
from app.core.timezone_engine import resolve_pool_window
from app.db.mock_db import MockDatabase
from app.db.models import CreditPoolStats, UserStatus
from app.identity.mock_identity import MockCloudIdentityGroupManager
from app.monitoring.mock_pool import MockCloudMonitoringPoolClient
from scripts.run_local_demo import seed_three_demo_users


def test_mock_database_initialization():
    """Verify MockDatabase initializes with 6 demo users and valid window_start_utc."""
    db = MockDatabase()
    users = db.list_users()
    assert len(users) == 6

    credit_pool = db.get_credit_pool()
    assert credit_pool is not None
    assert credit_pool.window_start_utc is not None
    assert credit_pool.next_reset_utc is not None
    assert credit_pool.next_reset_utc > credit_pool.window_start_utc

    for user in users:
        assert user.current_week.window_start_utc is not None
        assert user.current_week.window_start_utc == credit_pool.window_start_utc
        assert user.current_week.week_id.startswith("20")


def test_mock_pool_client_cycle_and_integration():
    """Verify MockCloudMonitoringPoolClient returns stats and syncs with MockDatabase."""
    db = MockDatabase()
    pool_client = MockCloudMonitoringPoolClient(db_client=db)

    stats = pool_client.get_pool_stats(force_refresh=True)
    assert stats.tier_key == "plus"
    assert stats.window_start_utc is not None
    assert stats.next_reset_utc == stats.window_start_utc + timedelta(days=7)

    # Verify stats saved to db
    saved_pool = db.get_credit_pool()
    assert saved_pool is not None
    assert saved_pool.window_start_utc == stats.window_start_utc

    # Verify set_mock_stats overrides cached stats and syncs to db
    custom_start = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    custom_stats = CreditPoolStats(
        tier_key="standard",
        tier_name="Gemini Enterprise Standard",
        usage_wtu=1_000_000,
        limit_wtu=40_000_000,
        usage_usd=2.00,
        limit_usd=80.00,
        utilization_pct=2.5,
        window_start_utc=custom_start,
        next_reset_utc=custom_start + timedelta(days=7),
    )
    pool_client.set_mock_stats(custom_stats)

    fetched = pool_client.get_pool_stats(force_refresh=False)
    assert fetched.tier_key == "standard"
    assert fetched.window_start_utc == custom_start

    db_pool = db.get_credit_pool()
    assert db_pool is not None
    assert db_pool.tier_key == "standard"


def test_mock_bigquery_usage_client():
    """Verify MockBigQueryUsageClient records start/end timestamps and custom records."""
    bq = MockBigQueryUsageClient()
    start = datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 10, 8, 0, 0, 0, tzinfo=UTC)

    records = bq.fetch_weekly_usage(start, end)
    assert len(records) > 0
    assert bq.last_query_start == start
    assert bq.last_query_end == end

    # Custom records
    bq.set_custom_records([])
    assert bq.fetch_weekly_usage(start, end) == []

    bq.reset()
    assert len(bq.fetch_weekly_usage(start, end)) > 0


def test_seed_three_demo_users_integration():
    """Verify scripts/run_local_demo.py seed_three_demo_users initializes users and pool stats."""
    db = get_db()
    identity = get_identity()

    seed_three_demo_users()

    users = db.list_users()
    assert len(users) == 4
    emails = {u.email for u in users}
    assert emails == {
        "alice.chen@example.com",
        "bob.martin@example.com",
        "charlie.davis@example.com",
        "infrasec@example.com",
    }

    requests = db.list_quota_requests()
    assert len(requests) >= 1
    assert any(r.user_email == "infrasec@example.com" for r in requests)

    credit_pool = db.get_credit_pool()
    assert credit_pool is not None
    assert credit_pool.window_start_utc is not None

    for user in users:
        assert user.current_week.window_start_utc == credit_pool.window_start_utc

    # Verify group assignments
    alice = db.get_user("alice.chen@example.com")
    bob = db.get_user("bob.martin@example.com")
    charlie = db.get_user("charlie.davis@example.com")

    assert alice.status == UserStatus.ACTIVE
    assert bob.status == UserStatus.ACTIVE
    assert charlie.status == UserStatus.AUTO_DISABLED

    assert identity.is_user_in_enabled_group(alice.email) is True
    assert identity.is_user_in_enabled_group(bob.email) is True
    assert identity.is_user_in_disabled_group(charlie.email) is True


def test_mock_evaluator_end_to_end_pool_aligned():
    """Verify QuotaEvaluator in mock environment runs full evaluation and resets correctly."""
    db = MockDatabase()
    bq = MockBigQueryUsageClient()
    identity = MockCloudIdentityGroupManager()
    pool_client = MockCloudMonitoringPoolClient(db_client=db)

    evaluator = QuotaEvaluator(
        db_client=db,
        bq_client=bq,
        identity_client=identity,
        pool_client=pool_client,
    )

    # 1. Run initial evaluation
    summary = evaluator.run_evaluation(is_publish=False)
    assert summary.users_evaluated == 6
    assert bq.last_query_start == db.get_credit_pool().window_start_utc

    # 2. Simulate Pool Advancement 7 days later
    current_pool = pool_client.get_pool_stats()
    new_start = current_pool.window_start_utc + timedelta(days=7)
    advanced_pool = CreditPoolStats(
        tier_key="plus",
        tier_name="Gemini Enterprise Plus",
        usage_wtu=500_000,
        limit_wtu=37_500_000,
        usage_usd=1.00,
        limit_usd=75.00,
        utilization_pct=1.3,
        window_start_utc=new_start,
        next_reset_utc=new_start + timedelta(days=7),
    )
    pool_client.set_mock_stats(advanced_pool)

    # Charlie was AUTO_DISABLED
    charlie_before = db.get_user("charlie.davis@example.com")
    assert charlie_before.status == UserStatus.AUTO_DISABLED

    # Evan was MANUALLY_DISABLED
    evan_before = db.get_user("evan.wright@example.com")
    assert evan_before.status == UserStatus.MANUALLY_DISABLED

    # Run evaluation after pool advancement
    reset_summary = evaluator.run_evaluation(is_publish=False)

    # Charlie should be reset to ACTIVE and unthrottled
    charlie_after = db.get_user("charlie.davis@example.com")
    assert charlie_after.status == UserStatus.ACTIVE
    assert charlie_after.current_week.window_start_utc == new_start

    # Charlie should have a snapshot archived for the previous cycle
    snapshots = db.list_weekly_snapshots("charlie.davis@example.com")
    assert len(snapshots) >= 1
    assert snapshots[-1].week_id.startswith("20")
    assert snapshots[-1].final_gross_cost_usd > 0

    # Evan must remain MANUALLY_DISABLED
    evan_after = db.get_user("evan.wright@example.com")
    assert evan_after.status == UserStatus.MANUALLY_DISABLED


def test_mock_database_group_storage_and_seeding():
    """Verify MockDatabase initializes with default quota groups, gatekeeper defaults, and CRUD."""
    from app.db.models import QuotaGroup

    db = MockDatabase()

    # 1. Verify default groups auto-seeded
    groups = db.list_groups()
    group_map = {g.group_id: g for g in groups}
    assert "developers" in group_map
    assert "business-users" in group_map

    dev_group = group_map["developers"]
    assert dev_group.display_name == "Developers"
    assert dev_group.weekly_quota_usd == 50.0
    assert dev_group.overage_buffer_usd == 10.0
    assert "Engineering" in dev_group.description

    biz_group = group_map["business-users"]
    assert biz_group.display_name == "Business Users"
    assert biz_group.weekly_quota_usd == 10.0
    assert biz_group.overage_buffer_usd == 2.0

    # 2. Verify AppConfig default gatekeeper emails
    config = db.get_config()
    assert config.enabled_group == "antigravity-active@example.com"
    assert config.disabled_group == "antigravity-throttled@example.com"

    # 3. Verify seeded mock users have group_id assigned
    alice = db.get_user("alice.chen@example.com")
    charlie = db.get_user("charlie.davis@example.com")
    assert alice is not None
    assert alice.group_id == "developers"
    assert charlie is not None
    assert charlie.group_id == "business-users"

    # 4. Verify aggregated group stats
    fetched_dev = db.get_group("developers")
    assert fetched_dev is not None
    assert fetched_dev.member_count >= 1
    assert fetched_dev.gross_spend_usd > 0
    assert fetched_dev.total_tokens > 0

    # 5. Create new group
    new_group = QuotaGroup(
        group_id="qa-testers",
        display_name="QA Testers",
        description="Quality assurance team",
        weekly_quota_usd=20.0,
        overage_buffer_usd=4.0,
        is_exempt=False,
    )
    created = db.create_group(new_group)
    assert created.group_id == "qa-testers"
    assert db.get_group("qa-testers") is not None

    # 6. Update group
    updated = db.update_group("qa-testers", {"weekly_quota_usd": 30.0, "display_name": "QA Engineers"})
    assert updated is not None
    assert updated.weekly_quota_usd == 30.0
    assert updated.display_name == "QA Engineers"

    # 7. Bulk assign members
    count = db.bulk_assign_group_members("qa-testers", ["alice.chen@example.com", "new.qa@example.com"])
    assert count == 2
    alice_updated = db.get_user("alice.chen@example.com")
    assert alice_updated.group_id == "qa-testers"
    new_qa = db.get_user("new.qa@example.com")
    assert new_qa is not None
    assert new_qa.group_id == "qa-testers"

    # 8. Delete group and member reassignment
    # Protection: Cannot delete "business-users" default group
    assert db.delete_group("business-users") is False

    # Deleting "qa-testers" reassigns members to "business-users"
    assert db.delete_group("qa-testers") is True
    assert db.get_group("qa-testers") is None
    reassigned_alice = db.get_user("alice.chen@example.com")
    assert reassigned_alice.group_id == "business-users"
    reassigned_qa = db.get_user("new.qa@example.com")
    assert reassigned_qa.group_id == "business-users"

