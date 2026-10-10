"""Production Google Cloud Monitoring client for Antigravity License Quota Pool."""

import logging
import zoneinfo
from datetime import UTC, datetime, timedelta
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

from app.db.models import CreditPoolStats

logger = logging.getLogger(__name__)

OVERAGE_WTU_UNIT_PRICE = 2.0 / 1_000_000  # $2.00 per 1M WTU ($0.000002 / WTU)

TIER_METRIC_MAP = {
    "plus": {
        "metric_base": "agentic_wtu_tier_enterprise_plus_pp_weekly_regional",
        "default_limit_wtu": 37_500_000,
        "display_name": "Gemini Enterprise Plus",
    },
    "standard": {
        "metric_base": "agentic_wtu_tier_enterprise_standard_pp_weekly_regional",
        "default_limit_wtu": 40_000_000,
        "display_name": "Gemini Enterprise Standard",
    },
    "flex": {
        "metric_base": "agentic_wtu_tier_consumption_only_pp_weekly_regional",
        "default_limit_wtu": 0,
        "display_name": "Gemini Enterprise Flex (PayGo)",
    },
}


class CloudMonitoringPoolClient:
    """Queries Cloud Monitoring v3 for Gemini Enterprise license rate metrics with caching and Firestore sync."""

    def __init__(
        self,
        project_id: str,
        db_client=None,
        cache_ttl_seconds: int = 300,
        location: str = "global",
    ):
        self.project_id = project_id
        self.db_client = db_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.location = location
        self._session: AuthorizedSession | None = None
        self._cache: CreditPoolStats | None = None
        self._cache_time: datetime | None = None

    def _get_session(self) -> AuthorizedSession:
        if self._session is None:
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/monitoring.read"])
            self._session = AuthorizedSession(creds)
        return self._session

    def _get_midnight_pacific_utc(self) -> tuple[datetime, datetime]:
        """Matches Cloud Console getMidnightPacific() window alignment."""
        pacific_tz = zoneinfo.ZoneInfo("America/Los_Angeles")
        now_pacific = datetime.now(pacific_tz)
        midnight_pacific = now_pacific.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = midnight_pacific.astimezone(UTC)
        end_utc = datetime.now(UTC)
        return start_utc, end_utc

    def _execute_query(self, params: list[tuple[str, str]] | dict[str, Any]) -> list[dict]:
        session = self._get_session()
        url = f"https://monitoring.googleapis.com/v3/projects/{self.project_id}/timeSeries"
        headers = {"X-Goog-User-Project": self.project_id}
        resp = session.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Cloud Monitoring API error ({resp.status_code}): {resp.text}")
        data = resp.json()
        return data.get("timeSeries", [])

    def _detect_active_tier(self) -> str:
        now = datetime.now(UTC)
        start_str = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        for tier_key in ["plus", "standard", "flex"]:
            metric_base = TIER_METRIC_MAP[tier_key]["metric_base"]
            filter_usage = (
                f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/net_usage" AND '
                f'resource.type = "discoveryengine.googleapis.com/Location" AND '
                f'metric.label.regional_location = "{self.location}"'
            )
            params_usage = {
                "filter": filter_usage,
                "interval.startTime": start_str,
                "interval.endTime": end_str,
            }
            try:
                series = self._execute_query(params_usage)
                if series and series[0].get("points"):
                    return tier_key
            except Exception:
                pass

            filter_limit = (
                f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/limit" AND '
                f'resource.type = "discoveryengine.googleapis.com/Location" AND '
                f'metric.label.regional_location = "{self.location}"'
            )
            params_limit = {
                "filter": filter_limit,
                "interval.startTime": start_str,
                "interval.endTime": end_str,
            }
            try:
                series = self._execute_query(params_limit)
                if series and series[0].get("points"):
                    val = int(series[0]["points"][0]["value"].get("int64Value", 0))
                    if val > 0:
                        return tier_key
            except Exception:
                pass

        return "plus"

    def _query_usage_wtu(self, metric_base: str) -> int:
        start_dt, end_dt = self._get_midnight_pacific_utc()
        interval_sec = int((end_dt - start_dt).total_seconds())
        if interval_sec <= 0:
            interval_sec = 60

        filter_expr = (
            f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/net_usage" AND '
            f'resource.type = "discoveryengine.googleapis.com/Location" AND '
            f'metric.label.regional_location = "{self.location}"'
        )

        params = [
            ("filter", filter_expr),
            ("interval.startTime", start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("interval.endTime", end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("aggregation.alignmentPeriod", f"{interval_sec}s"),
            ("aggregation.perSeriesAligner", "ALIGN_NEXT_OLDER"),
            ("aggregation.crossSeriesReducer", "REDUCE_SUM"),
            ("aggregation.groupByFields", "resource.label.service"),
            ("aggregation.groupByFields", "metric.type"),
        ]

        series = self._execute_query(params)
        if series and series[0].get("points"):
            return int(series[0]["points"][0]["value"].get("int64Value", 0))
        return 0

    def _query_limit_wtu(self, metric_base: str, fallback_limit: int) -> int:
        start_dt, end_dt = self._get_midnight_pacific_utc()
        filter_expr = (
            f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/limit" AND '
            f'resource.type = "discoveryengine.googleapis.com/Location" AND '
            f'metric.label.regional_location = "{self.location}"'
        )
        params = {
            "filter": filter_expr,
            "interval.startTime": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval.endTime": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        series = self._execute_query(params)
        if series and series[0].get("points"):
            val = int(series[0]["points"][0]["value"].get("int64Value", 0))
            if val > 0:
                return val
        return fallback_limit

    def _query_window_timestamps(self, metric_base: str) -> tuple[datetime, datetime]:
        start_dt, end_dt = self._get_midnight_pacific_utc()
        filter_expr = (
            f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/net_usage" AND '
            f'resource.type = "discoveryengine.googleapis.com/Location" AND '
            f'metric.label.regional_location = "{self.location}"'
        )
        params = {
            "filter": filter_expr,
            "interval.startTime": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval.endTime": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        series_list = self._execute_query(params)
        latest_start_sec = 0
        for ts in series_list:
            w_start = ts.get("metric", {}).get("labels", {}).get("window_start_time")
            if w_start:
                latest_start_sec = max(latest_start_sec, int(w_start))

        if latest_start_sec > 0:
            start_time_dt = datetime.fromtimestamp(latest_start_sec, tz=UTC)
        else:
            start_time_dt = start_dt

        return start_time_dt, start_time_dt + timedelta(days=7)

    def _fetch_from_monitoring_api(self) -> CreditPoolStats:
        tier_key = self._detect_active_tier()
        tier_cfg = TIER_METRIC_MAP[tier_key]
        metric_base = tier_cfg["metric_base"]
        tier_display_name = tier_cfg["display_name"]

        usage_wtu = self._query_usage_wtu(metric_base)
        limit_wtu = self._query_limit_wtu(metric_base, tier_cfg["default_limit_wtu"])

        usage_usd = round(usage_wtu * OVERAGE_WTU_UNIT_PRICE, 2)
        limit_usd = round(limit_wtu * OVERAGE_WTU_UNIT_PRICE, 2)
        pct = round((usage_usd / limit_usd * 100), 1) if limit_usd > 0 else 0.0

        start_dt, reset_dt = self._query_window_timestamps(metric_base)

        return CreditPoolStats(
            tier_key=tier_key,
            tier_name=tier_display_name,
            usage_wtu=usage_wtu,
            limit_wtu=limit_wtu,
            usage_usd=usage_usd,
            limit_usd=limit_usd,
            utilization_pct=pct,
            window_start_utc=start_dt,
            next_reset_utc=reset_dt,
            last_synced_at=datetime.now(UTC),
        )

    def get_pool_stats(self, force_refresh: bool = False) -> CreditPoolStats:
        now = datetime.now(UTC)
        if not force_refresh and self._cache is not None and self._cache_time is not None:
            elapsed = (now - self._cache_time).total_seconds()
            if elapsed < self.cache_ttl_seconds:
                return self._cache

        try:
            stats = self._fetch_from_monitoring_api()
            self._cache = stats
            self._cache_time = now
            if self.db_client:
                self.db_client.save_credit_pool(stats)
            return stats
        except Exception as e:
            logger.warning(f"Error fetching Cloud Monitoring metrics: {e}. Attempting database fallback.")
            if self.db_client:
                persisted = self.db_client.get_credit_pool()
                if persisted:
                    self._cache = persisted
                    self._cache_time = now
                    return persisted

            if self._cache:
                return self._cache

            # Ultimate fallback if no data in DB or API
            fallback = CreditPoolStats(last_synced_at=now)
            self._cache = fallback
            self._cache_time = now
            return fallback
