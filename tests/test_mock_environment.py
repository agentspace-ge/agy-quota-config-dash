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
    """Verify MockDatabase initializes with 5 demo users and valid window_start_utc."""
    db = MockDatabase()
    users = db.list_users()
    assert len(users) == 5

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
    assert len(users) == 3
    emails = {u.email for u in users}
    assert emails == {
        "alice.chen@example.com",
        "bob.martin@example.com",
        "charlie.davis@example.com",
    }

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
    assert summary.users_evaluated == 5
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
