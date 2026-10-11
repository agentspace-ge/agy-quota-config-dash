"""Mock Cloud Monitoring Pool Client for testing and local sandbox."""

from datetime import UTC, datetime, timedelta

from app.db.models import CreditPoolStats


class MockCloudMonitoringPoolClient:
    """Mock client simulating Cloud Monitoring quota rate queries."""

    def __init__(self, db_client=None):
        self.db_client = db_client
        self._cached_stats: CreditPoolStats | None = None

    def get_pool_stats(self, force_refresh: bool = False) -> CreditPoolStats:
        now = datetime.now(UTC)
        if not force_refresh and self._cached_stats is not None:
            return self._cached_stats

        # Compute realistic start/reset timestamps matching current weekly cycle
        days_since_cycle = (now.weekday() - 5) % 7  # Align to Saturday cycle
        cycle_start = (now - timedelta(days=days_since_cycle)).replace(hour=12, minute=47, second=20, microsecond=0)
        cycle_reset = cycle_start + timedelta(days=7)

        stats = CreditPoolStats(
            tier_key="plus",
            tier_name="Gemini Enterprise Plus",
            usage_wtu=3_900_567,
            limit_wtu=37_500_000,
            usage_usd=7.80,
            limit_usd=75.00,
            utilization_pct=10.4,
            window_start_utc=cycle_start,
            next_reset_utc=cycle_reset,
            last_synced_at=now,
        )

        self._cached_stats = stats
        if self.db_client:
            self.db_client.save_credit_pool(stats)

        return stats

    def set_mock_stats(self, stats: CreditPoolStats):
        self._cached_stats = stats
        if self.db_client:
            self.db_client.save_credit_pool(stats)

