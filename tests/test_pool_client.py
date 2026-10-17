"""Unit and integration tests for Cloud Monitoring Credit Pool Client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.db.mock_db import MockDatabase
from app.db.models import CreditPoolStats
from app.monitoring.mock_pool import MockCloudMonitoringPoolClient
from app.monitoring.pool_client import CloudMonitoringPoolClient


def test_mock_pool_client():
    db = MockDatabase()
    client = MockCloudMonitoringPoolClient(db_client=db)
    stats = client.get_pool_stats()

    assert stats.tier_key == "plus"
    assert stats.tier_name == "Gemini Enterprise Plus"
    assert stats.usage_wtu == 3_900_567
    assert stats.limit_wtu == 37_500_000
    assert stats.usage_usd == 7.80
    assert stats.limit_usd == 75.00
    assert stats.utilization_pct == 10.4
    assert stats.window_start_utc is not None
    assert stats.next_reset_utc is not None
    assert stats.next_reset_utc > stats.window_start_utc
    assert stats.last_synced_at is not None

    # Verify persisted to DB
    persisted = db.get_credit_pool()
    assert persisted is not None
    assert persisted.usage_wtu == stats.usage_wtu


def test_pool_client_in_memory_caching():
    db = MockDatabase()
    client = CloudMonitoringPoolClient(
        project_id="test-proj",
        db_client=db,
        cache_ttl_seconds=60,
    )

    fake_stats = CreditPoolStats(
        tier_key="plus",
        tier_name="Gemini Enterprise Plus",
        usage_wtu=5_000_000,
        limit_wtu=37_500_000,
        usage_usd=10.0,
        limit_usd=75.0,
        utilization_pct=13.3,
        window_start_utc=datetime.now(UTC),
        next_reset_utc=datetime.now(UTC) + timedelta(days=7),
        last_synced_at=datetime.now(UTC),
    )

    with patch.object(client, "_fetch_from_monitoring_api", return_value=fake_stats) as mock_fetch:
        # First call -> fetches
        s1 = client.get_pool_stats()
        assert s1.usage_wtu == 5_000_000
        assert mock_fetch.call_count == 1

        # Second call immediately -> uses in-memory cache
        s2 = client.get_pool_stats()
        assert s2.usage_wtu == 5_000_000
        assert mock_fetch.call_count == 1

        # Force refresh -> bypasses cache and calls fetch again
        s3 = client.get_pool_stats(force_refresh=True)
        assert s3.usage_wtu == 5_000_000
        assert mock_fetch.call_count == 2


def test_pool_client_fallback_to_db_on_api_error():
    db = MockDatabase()
    saved_stats = CreditPoolStats(
        tier_key="standard",
        tier_name="Gemini Enterprise Standard",
        usage_wtu=1_000_000,
        limit_wtu=40_000_000,
        usage_usd=2.0,
        limit_usd=80.0,
        utilization_pct=2.5,
        window_start_utc=datetime.now(UTC),
        next_reset_utc=datetime.now(UTC) + timedelta(days=7),
        last_synced_at=datetime.now(UTC),
    )
    db.save_credit_pool(saved_stats)

    client = CloudMonitoringPoolClient(
        project_id="test-proj",
        db_client=db,
        cache_ttl_seconds=60,
    )

    with patch.object(client, "_fetch_from_monitoring_api", side_effect=RuntimeError("Cloud Monitoring unavailable")):
        stats = client.get_pool_stats(force_refresh=True)
        assert stats.tier_key == "standard"
        assert stats.usage_wtu == 1_000_000
        assert stats.usage_usd == 2.0


def test_kpi_endpoint_includes_credit_pool(client):
    response = client.get("/api/evaluator/kpis")
    assert response.status_code == 200
    data = response.json()
    assert "credit_pool" in data
    pool = data["credit_pool"]
    assert pool is not None
    assert pool["tier_name"] == "Gemini Enterprise Plus"
    assert pool["usage_wtu"] > 0
    assert pool["limit_wtu"] > 0
    assert pool["usage_usd"] > 0
    assert pool["limit_usd"] > 0
    assert pool["utilization_pct"] > 0
    assert pool["window_start_utc"] is not None
    assert pool["next_reset_utc"] is not None


def test_query_window_timestamps_aggregated():
    db = MockDatabase()
    client = CloudMonitoringPoolClient(
        project_id="test-proj",
        db_client=db,
    )
    # Simulated aggregated response grouping by window_start_time
    mock_aggregated_series = [
        {"metric": {"labels": {"window_start_time": "1791212763"}}},
        {"metric": {"labels": {"window_start_time": "1791829558"}}},
    ]
    with patch.object(client, "_execute_query", return_value=mock_aggregated_series):
        start_dt, reset_dt = client._query_window_timestamps("agentic_wtu_tier_enterprise_plus_pp_weekly_regional")
        assert start_dt == datetime.fromtimestamp(1791829558, tz=UTC)
        assert reset_dt == start_dt + timedelta(days=7)

