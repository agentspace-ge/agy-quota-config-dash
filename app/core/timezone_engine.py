"""Timezone and weekly boundary calculation engine."""

from datetime import UTC, datetime, time, timedelta

import pytz


def get_timezone_obj(tz_name: str) -> pytz.BaseTzInfo:
    """Safely get pytz timezone object with fallback to UTC."""
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.UTC


def get_current_week_window(
    tz_name: str = "America/Los_Angeles",
    now_dt: datetime | None = None,
) -> tuple[str, datetime, datetime, datetime]:
    """Calculate the current weekly quota window starting at Monday 00:00:00 in the given timezone.

    Returns:
        week_id: ISO week identifier e.g. "2026-W35"
        start_utc: Datetime in UTC representing Monday 00:00:00 in the target timezone
        end_utc: Datetime in UTC representing Sunday 23:59:59 in the target timezone
        current_utc: Current datetime in UTC
    """
    tz = get_timezone_obj(tz_name)

    if now_dt is None:
        now_utc = datetime.now(UTC)
    else:
        if now_dt.tzinfo is None:
            now_utc = now_dt.replace(tzinfo=UTC)
        else:
            now_utc = now_dt.astimezone(UTC)

    # Convert current UTC time to application timezone
    now_local = now_utc.astimezone(tz)

    # Monday of the current week in local timezone
    # weekday(): Monday is 0 and Sunday is 6
    days_since_monday = now_local.weekday()
    monday_date = (now_local - timedelta(days=days_since_monday)).date()

    # Start: Monday 00:00:00 local
    monday_midnight_local = tz.localize(datetime.combine(monday_date, time.min))
    start_utc = monday_midnight_local.astimezone(UTC)

    # End: Sunday 23:59:59.999999 local
    sunday_date = monday_date + timedelta(days=6)
    sunday_end_local = tz.localize(datetime.combine(sunday_date, time.max))
    end_utc = sunday_end_local.astimezone(UTC)

    # ISO week string: YYYY-Www (e.g. 2026-W35)
    iso_year, iso_week, _ = now_local.isocalendar()
    week_id = f"{iso_year}-W{iso_week:02d}"

    return week_id, start_utc, end_utc, now_utc


def is_new_week(last_week_id: str | None, current_week_id: str) -> bool:
    """Check if the recorded week ID differs from current week ID."""
    if not last_week_id:
        return False
    return last_week_id != current_week_id


def resolve_pool_window(
    pool_stats: Any = None,
    fallback_timezone: str = "America/Los_Angeles",
    now_dt: datetime | None = None,
) -> tuple[str, datetime, datetime, datetime]:
    """Resolve the active weekly quota window based on upstream CreditPoolStats or fallback to calendar Monday.

    Returns:
        week_id: ISO week string, e.g. "2026-W41"
        start_utc: UTC datetime representing cycle start
        end_utc: UTC datetime representing cycle reset/end
        now_utc: Current UTC datetime
    """
    if now_dt is None:
        now_utc = datetime.now(UTC)
    else:
        now_utc = now_dt.replace(tzinfo=UTC) if now_dt.tzinfo is None else now_dt.astimezone(UTC)

    if pool_stats is not None and getattr(pool_stats, "window_start_utc", None):
        start_utc = pool_stats.window_start_utc
        if start_utc.tzinfo is None:
            start_utc = start_utc.replace(tzinfo=UTC)
        else:
            start_utc = start_utc.astimezone(UTC)

        end_utc = getattr(pool_stats, "next_reset_utc", None)
        if end_utc is None:
            end_utc = start_utc + timedelta(days=7)
        elif end_utc.tzinfo is None:
            end_utc = end_utc.replace(tzinfo=UTC)
        else:
            end_utc = end_utc.astimezone(UTC)

        iso_year, iso_week, _ = start_utc.isocalendar()
        week_id = f"{iso_year}-W{iso_week:02d}"
        return week_id, start_utc, end_utc, now_utc

    return get_current_week_window(fallback_timezone, now_dt)


def is_new_pool_cycle(
    prev_window_start_utc: datetime | None,
    current_window_start_utc: datetime,
    now_utc: datetime | None = None,
    next_reset_utc: datetime | None = None,
) -> bool:
    """Determine if a new pool cycle has begun with monotonic and proactive checks.

    Rules:
    1. If prev_window_start_utc is None: False (first cycle recorded, do not wipe spend).
    2. Monotonic forward check: if current_window_start_utc - prev_window_start_utc >= 5 days: True.
    3. Hybrid proactive check: if now_utc >= next_reset_utc and next_reset_utc > prev_window_start_utc: True.
    4. Otherwise: False.
    """
    if prev_window_start_utc is None or current_window_start_utc is None:
        return False

    if prev_window_start_utc.tzinfo is None:
        prev_window_start_utc = prev_window_start_utc.replace(tzinfo=UTC)
    if current_window_start_utc.tzinfo is None:
        current_window_start_utc = current_window_start_utc.replace(tzinfo=UTC)

    # 1. Forward advancement by at least 5 days (guards against midnight jitter or backward clock drift)
    delta_start = (current_window_start_utc - prev_window_start_utc).total_seconds()
    if delta_start >= 5 * 86400:
        return True

    # 2. Hybrid proactive expiry: if current time now has passed next_reset_utc
    if now_utc is not None and next_reset_utc is not None:
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=UTC)
        if next_reset_utc.tzinfo is None:
            next_reset_utc = next_reset_utc.replace(tzinfo=UTC)
        if now_utc >= next_reset_utc and next_reset_utc > prev_window_start_utc:
            return True

    return False

