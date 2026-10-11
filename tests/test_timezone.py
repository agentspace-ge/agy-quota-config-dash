"""Unit tests for timezone handling and weekly window boundaries."""

from datetime import UTC, datetime

from app.core.timezone_engine import get_current_week_window, is_new_pool_cycle, is_new_week, resolve_pool_window
from app.db.models import CreditPoolStats
from datetime import timedelta


def test_get_current_week_window_monday_start():
    # Thursday, August 27, 2026, 12:00:00 UTC
    dt = datetime(2026, 8, 27, 12, 0, 0, tzinfo=UTC)
    week_id, start_utc, end_utc, now_utc = get_current_week_window("America/Los_Angeles", dt)

    assert week_id == "2026-W35"

    # Monday in Los Angeles was August 24, 2026
    # PDT is UTC-7, so Monday 00:00:00 PDT is Monday 07:00:00 UTC
    assert start_utc.year == 2026
    assert start_utc.month == 8
    assert start_utc.day == 24
    assert start_utc.hour == 7
    assert start_utc.minute == 0


def test_is_new_week():
    assert is_new_week("2026-W34", "2026-W35") is True
    assert is_new_week("2026-W35", "2026-W35") is False
    assert is_new_week(None, "2026-W35") is False


def test_resolve_pool_window_with_pool_stats():
    # Pool start time: Sunday, Oct 11, 2026 13:06:56 UTC
    start_time = datetime(2026, 10, 11, 13, 6, 56, tzinfo=UTC)
    reset_time = start_time + timedelta(days=7)
    now_time = datetime(2026, 10, 13, 10, 0, 0, tzinfo=UTC)

    stats = CreditPoolStats(
        window_start_utc=start_time,
        next_reset_utc=reset_time,
    )

    week_id, start_utc, end_utc, now_utc = resolve_pool_window(stats, "America/Los_Angeles", now_time)

    assert week_id == "2026-W41"
    assert start_utc == start_time
    assert end_utc == reset_time
    assert now_utc == now_time


def test_resolve_pool_window_fallback_when_none():
    now_time = datetime(2026, 8, 27, 12, 0, 0, tzinfo=UTC)
    week_id, start_utc, end_utc, now_utc = resolve_pool_window(None, "America/Los_Angeles", now_time)

    assert week_id == "2026-W35"
    assert start_utc.year == 2026
    assert start_utc.month == 8
    assert start_utc.day == 24
    assert start_utc.hour == 7


def test_is_new_pool_cycle_monotonic_and_hybrid():
    t0 = datetime(2026, 10, 11, 13, 6, 56, tzinfo=UTC)
    t1 = t0 + timedelta(days=7)
    reset_t0 = t0 + timedelta(days=7)

    # 1. First cycle ever recorded (prev is None) -> False (smooth re-alignment, no premature reset)
    assert is_new_pool_cycle(None, t0, t0, reset_t0) is False

    # 2. Same window -> False
    assert is_new_pool_cycle(t0, t0, t0 + timedelta(days=2), reset_t0) is False

    # 3. Flapping / earlier timestamp or small jitter (< 5 days) -> False (monotonic guard)
    assert is_new_pool_cycle(t0, t0 - timedelta(hours=2), t0, reset_t0) is False
    assert is_new_pool_cycle(t0, t0 + timedelta(days=2), t0 + timedelta(days=2), reset_t0) is False

    # 4. Valid 7-day forward advancement -> True
    assert is_new_pool_cycle(t0, t1, t1, t1 + timedelta(days=7)) is True

    # 5. Hybrid proactive expiry: current time now >= next_reset_utc even if upstream hasn't reported new start
    now_after_expiry = reset_t0 + timedelta(minutes=5)
    assert is_new_pool_cycle(t0, t0, now_after_expiry, reset_t0) is True

