#!/usr/bin/env python3
"""Validates Antigravity Weekly Quota matching Cloud Console QuotaFetcherService.

Features:
  - Automatic detection of active Gemini Enterprise tier (Plus, Standard, or Flex)
  - Displays detected Tier on top of the output
  - Exact Cloud Console Usage & Spending matching calculation
"""

from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
import sys
from typing import Any
import urllib.parse
import urllib.request
import zoneinfo

# Unit price from dev_tools_config.ts: $2.00 per 1M WTU ($0.000002 / WTU)
OVERAGE_WTU_UNIT_PRICE = 2.0 / 1_000_000

# Metric definitions by subscription tier
TIER_METRIC_MAP = {
    "plus": {
        "metric_base": "agentic_wtu_tier_enterprise_plus_pp_weekly_regional",
        "default_limit_wtu": 37_500_000,  # 5 seats @ $15/seat/month ($75/week baseline)
        "display_name": "Gemini Enterprise Plus",
    },
    "standard": {
        "metric_base": "agentic_wtu_tier_enterprise_standard_pp_weekly_regional",
        "default_limit_wtu": 40_000_000,  # Baseline allocation for Standard tier
        "display_name": "Gemini Enterprise Standard",
    },
    "flex": {
        "metric_base": "agentic_wtu_tier_consumption_only_pp_weekly_regional",
        "default_limit_wtu": 0,
        "display_name": "Gemini Enterprise Flex (PayGo)",
    },
}


def get_token() -> str:
  """Retrieves an access token via ADC or gcloud."""
  for cmd in [
      ["gcloud", "auth", "application-default", "print-access-token"],
      ["gcloud", "auth", "print-access-token"],
  ]:
    try:
      token = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
      if token:
        return token
    except Exception:
      continue
  sys.exit("Error: Run 'gcloud auth application-default login' to authenticate.")


def get_default_project_id() -> str:
  """Resolves project ID from environment variables or active gcloud configuration."""
  env_project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
      "CLOUDSDK_CORE_PROJECT"
  )
  if env_project:
    return env_project
  try:
    return subprocess.check_output(
        ["gcloud", "config", "get-value", "project"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
  except Exception:
    return ""


def get_midnight_pacific_utc() -> tuple[datetime, datetime]:
  """Computes Midnight Pacific time today in UTC (matching Cloud Console getMidnightPacific())."""
  pacific_tz = zoneinfo.ZoneInfo("America/Los_Angeles")
  now_pacific = datetime.now(pacific_tz)
  midnight_pacific = now_pacific.replace(hour=0, minute=0, second=0, microsecond=0)

  start_utc = midnight_pacific.astimezone(timezone.utc)
  end_utc = datetime.now(timezone.utc)
  return start_utc, end_utc


def _execute_monitoring_query(
    project_id: str, token: str, params: list[tuple[str, str]]
) -> list[dict]:
  """Performs an authenticated GET query against Cloud Monitoring v3 timeSeries."""
  url = f"https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries?{urllib.parse.urlencode(params)}"
  req = urllib.request.Request(
      url,
      headers={
          "Authorization": f"Bearer {token}",
          "X-Goog-User-Project": project_id,
      },
  )
  try:
    with urllib.request.urlopen(req) as resp:
      data = json.loads(resp.read().decode())
      return data.get("timeSeries", [])
  except urllib.error.HTTPError as e:
    err_body = e.read().decode()
    raise RuntimeError(f"Cloud Monitoring API error ({e.code}): {err_body}") from e


def detect_active_tier(project_id: str, token: str, location: str = "global") -> str:
  """Auto-detects the active license tier by checking exact tier metrics sequentially."""
  now = datetime.now(timezone.utc)
  start_str = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
  end_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

  for tier_key in ["plus", "standard", "flex"]:
    metric_base = TIER_METRIC_MAP[tier_key]["metric_base"]

    # 1. Check if net_usage has points
    filter_usage = (
        f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/net_usage" AND '
        f'resource.type = "discoveryengine.googleapis.com/Location" AND '
        f'metric.label.regional_location = "{location}"'
    )
    params_usage = [
        ("filter", filter_usage),
        ("interval.startTime", start_str),
        ("interval.endTime", end_str),
    ]
    try:
      series = _execute_monitoring_query(project_id, token, params_usage)
      if series and series[0].get("points"):
        return tier_key
    except Exception:
      pass

    # 2. Check if limit has points > 0
    filter_limit = (
        f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/limit" AND '
        f'resource.type = "discoveryengine.googleapis.com/Location" AND '
        f'metric.label.regional_location = "{location}"'
    )
    params_limit = [
        ("filter", filter_limit),
        ("interval.startTime", start_str),
        ("interval.endTime", end_str),
    ]
    try:
      series = _execute_monitoring_query(project_id, token, params_limit)
      if series and series[0].get("points"):
        val = int(series[0]["points"][0]["value"].get("int64Value", 0))
        if val > 0:
          return tier_key
    except Exception:
      pass

  return "plus"  # Default fallback


def query_console_usage(project_id: str, token: str, metric_base: str, location: str) -> int:
  """Fetches exact WTU usage using the Cloud Console's ALIGN_NEXT_OLDER & REDUCE_SUM query."""
  start_dt, end_dt = get_midnight_pacific_utc()
  interval_sec = int((end_dt - start_dt).total_seconds())

  filter_expr = (
      f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/net_usage" AND '
      f'resource.type = "discoveryengine.googleapis.com/Location" AND '
      f'metric.label.regional_location = "{location}"'
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

  series = _execute_monitoring_query(project_id, token, params)
  if series and series[0].get("points"):
    return int(series[0]["points"][0]["value"].get("int64Value", 0))
  return 0


def query_active_limit_wtu(
    project_id: str, token: str, metric_base: str, location: str, fallback_limit: int
) -> int:
  """Queries the limit metric from Cloud Monitoring or falls back to configured baseline."""
  start_dt, end_dt = get_midnight_pacific_utc()
  filter_expr = (
      f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/limit" AND '
      f'resource.type = "discoveryengine.googleapis.com/Location" AND '
      f'metric.label.regional_location = "{location}"'
  )
  params = [
      ("filter", filter_expr),
      ("interval.startTime", start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
      ("interval.endTime", end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
  ]
  series = _execute_monitoring_query(project_id, token, params)
  if series and series[0].get("points"):
    val = int(series[0]["points"][0]["value"].get("int64Value", 0))
    if val > 0:
      return val
  return fallback_limit


def query_window_timestamps(
    project_id: str, token: str, metric_base: str, location: str
) -> tuple[datetime, datetime]:
  """Retrieves the active window_start_time label and derives the next reset time (+7d)."""
  now = datetime.now(timezone.utc)
  start_str = (now - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
  end_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

  filter_expr = (
      f'metric.type = "discoveryengine.googleapis.com/quota/ratev2/{metric_base}/net_usage" AND '
      f'resource.type = "discoveryengine.googleapis.com/Location" AND '
      f'metric.label.regional_location = "{location}"'
  )

  params = [
      ("filter", filter_expr),
      ("interval.startTime", start_str),
      ("interval.endTime", end_str),
  ]

  series_list = _execute_monitoring_query(project_id, token, params)
  latest_start_sec = 0
  for ts in series_list:
    w_start = ts.get("metric", {}).get("labels", {}).get("window_start_time")
    if w_start:
      latest_start_sec = max(latest_start_sec, int(w_start))

  if latest_start_sec > 0:
    start_time_dt = datetime.fromtimestamp(latest_start_sec, tz=timezone.utc)
  else:
    start_dt, _ = get_midnight_pacific_utc()
    start_time_dt = start_dt

  return start_time_dt, start_time_dt + timedelta(days=7)


def main():
  import argparse
  parser = argparse.ArgumentParser(description="Validates Antigravity Weekly Quota matching Cloud Console QuotaFetcherService.")
  parser.add_argument("project_id", nargs="?", default="", help="GCP Project ID (defaults to gcloud active project)")
  parser.add_argument("--sync-firestore", "--save", dest="sync_firestore", action="store_true", help="Synchronize active CreditPoolStats to Firestore (config/credit_pool)")
  args = parser.parse_args()

  default_project = get_default_project_id()
  project_id = args.project_id or (default_project or "ge-ent-app-demo")
  location = "global"

  token = get_token()

  # 1. Auto-detect active subscription tier
  tier_key = detect_active_tier(project_id, token, location)
  tier_cfg = TIER_METRIC_MAP[tier_key]
  metric_base = tier_cfg["metric_base"]
  tier_display_name = tier_cfg["display_name"]

  # 2. Fetch usage and limit
  usage_wtu = query_console_usage(project_id, token, metric_base, location)
  limit_wtu = query_active_limit_wtu(
      project_id, token, metric_base, location, tier_cfg["default_limit_wtu"]
  )

  usage_usd = round(usage_wtu * OVERAGE_WTU_UNIT_PRICE * 100) / 100
  limit_usd = round(limit_wtu * OVERAGE_WTU_UNIT_PRICE * 100) / 100
  pct = (usage_usd / limit_usd * 100) if limit_usd > 0 else 0.0

  # 3. Fetch window start and reset timestamps
  start_dt, reset_dt = query_window_timestamps(project_id, token, metric_base, location)
  start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
  reset_str = reset_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

  # 4. Formatted printout with Tier on top
  print("=" * 60)
  print(f" Cloud Console Quota Matcher: {project_id}")
  print("=" * 60)
  print(f"Tier: {tier_display_name}")
  print(f"• Current Raw Token Usage (WTU)               : {usage_wtu:,} WTU")
  print(f"• Weekly Toke Limit (WTU)                     : {limit_wtu:,} WTU")
  print(f"• Org Wide Weekly Credit Pool Usage (USD)     : ${usage_usd:.2f}")
  print(f"• Org Wide Weekly Credit Limit (USD)          : ${limit_usd:.2f}")
  print(f"• Org Wide Weekly Credit Pool Utilization (%) : {pct:.1f}%")
  print(f"• Current Weekly Credit Pool Start Time (UTC) : {start_str}")
  print(f"• Next Weekly Credit Pool Reset Time (UTC)    : {reset_str}")
  print("=" * 60)

  if args.sync_firestore:
    try:
      from google.cloud import firestore
      fs = firestore.Client(project=project_id)
      doc_data = {
          "tier_key": tier_key,
          "tier_name": tier_display_name,
          "usage_wtu": usage_wtu,
          "limit_wtu": limit_wtu,
          "usage_usd": usage_usd,
          "limit_usd": limit_usd,
          "utilization_pct": pct,
          "window_start_utc": start_dt,
          "next_reset_utc": reset_dt,
          "last_synced_at": datetime.now(timezone.utc),
      }
      fs.collection("config").document("credit_pool").set(doc_data)
      print("✓ Successfully synchronized CreditPoolStats to Firestore (config/credit_pool)")
    except Exception as e:
      print(f"✗ Failed to sync to Firestore: {e}", file=sys.stderr)


if __name__ == "__main__":
  main()

