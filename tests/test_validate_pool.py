"""Tests for validate_pool.py script utility functions and Firestore sync logic."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from scripts.validate_pool import (
    OVERAGE_WTU_UNIT_PRICE,
    TIER_METRIC_MAP,
    get_midnight_pacific_utc,
    main,
    query_window_timestamps,
)


def test_tier_metric_map_definitions():
    """Verify standard tier configurations are correctly mapped."""
    assert "plus" in TIER_METRIC_MAP
    assert "standard" in TIER_METRIC_MAP
    assert TIER_METRIC_MAP["plus"]["default_limit_wtu"] == 37_500_000
    assert TIER_METRIC_MAP["standard"]["default_limit_wtu"] == 40_000_000
    assert OVERAGE_WTU_UNIT_PRICE == 0.000002


def test_get_midnight_pacific_utc():
    """Verify get_midnight_pacific_utc returns a valid UTC datetime aligned to Pacific."""
    start_dt, end_dt = get_midnight_pacific_utc()
    assert start_dt.tzinfo is not None
    assert end_dt.tzinfo is not None
    assert end_dt > start_dt


@patch("scripts.validate_pool._execute_monitoring_query")
def test_query_window_timestamps_from_metric(mock_query):
    """Verify query_window_timestamps extracts window_start_time correctly from time series."""
    # window_start_time label timestamp
    ts_seconds = 1728132440
    mock_query.return_value = [
        {
            "metric": {
                "labels": {
                    "window_start_time": str(ts_seconds),
                }
            }
        }
    ]

    start_dt, reset_dt = query_window_timestamps("test-project", "fake-token", "fake-metric", "global")
    expected_start = datetime.fromtimestamp(ts_seconds, tz=UTC)
    assert start_dt == expected_start
    assert reset_dt == expected_start + timedelta(days=7)


@patch("scripts.validate_pool._execute_monitoring_query")
def test_query_window_timestamps_fallback(mock_query):
    """Verify fallback to Pacific midnight when no window_start_time label is present."""
    mock_query.return_value = []

    start_dt, reset_dt = query_window_timestamps("test-project", "fake-token", "fake-metric", "global")
    assert start_dt is not None
    assert reset_dt == start_dt + timedelta(days=7)


@patch("scripts.validate_pool.get_token", return_value="fake-token")
@patch("scripts.validate_pool.detect_active_tier", return_value="plus")
@patch("scripts.validate_pool.query_console_usage", return_value=3_900_000)
@patch("scripts.validate_pool.query_active_limit_wtu", return_value=37_500_000)
@patch("scripts.validate_pool.query_window_timestamps")
@patch("sys.argv", ["validate_pool.py", "test-proj"])
def test_validate_pool_main_without_sync(mock_window, mock_limit, mock_usage, mock_tier, mock_tok):
    """Verify main() prints validation without syncing to Firestore if flag not set."""
    now = datetime.now(UTC)
    mock_window.return_value = (now - timedelta(days=2), now + timedelta(days=5))

    with patch("google.cloud.firestore.Client") as mock_fs:
        main()
        mock_fs.assert_not_called()


@patch("scripts.validate_pool.get_token", return_value="fake-token")
@patch("scripts.validate_pool.detect_active_tier", return_value="plus")
@patch("scripts.validate_pool.query_console_usage", return_value=3_900_000)
@patch("scripts.validate_pool.query_active_limit_wtu", return_value=37_500_000)
@patch("scripts.validate_pool.query_window_timestamps")
@patch("sys.argv", ["validate_pool.py", "test-proj", "--sync-firestore"])
def test_validate_pool_main_with_sync(mock_window, mock_limit, mock_usage, mock_tier, mock_tok):
    """Verify main() syncs to Firestore when --sync-firestore is passed."""
    start_time = datetime(2026, 10, 8, 12, 0, 0, tzinfo=UTC)
    reset_time = start_time + timedelta(days=7)
    mock_window.return_value = (start_time, reset_time)

    mock_doc = MagicMock()
    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_col

    with patch("google.cloud.firestore.Client", return_value=mock_client):
        main()
        mock_col.document.assert_called_with("credit_pool")
        mock_doc.set.assert_called_once()
        saved_data = mock_doc.set.call_args[0][0]
        assert saved_data["tier_key"] == "plus"
        assert saved_data["window_start_utc"] == start_time
        assert saved_data["next_reset_utc"] == reset_time
