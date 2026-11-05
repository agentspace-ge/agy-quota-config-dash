"""Unit tests for cost modeling, hinge points, and credit mechanics."""

from app.core.cost_model import (
    calculate_blended_rate_per_million,
    calculate_model_spend,
    calculate_total_usage_costs,
    match_model_pricing,
)
from app.db.models import DEFAULT_MODEL_PRICING


def test_match_model_pricing():
    # Exact and pattern matching tests
    pricing = match_model_pricing("gemini-3-pro", DEFAULT_MODEL_PRICING)
    assert pricing.display_name == "Gemini 3.1 Pro / 3.0 Pro"

    pricing_flash = match_model_pricing("models/gemini-3.6-flash-preview", DEFAULT_MODEL_PRICING)
    assert pricing_flash.display_name == "Gemini 3.6 / 3.7 Flash"

    pricing_fallback = match_model_pricing("unknown-custom-model", DEFAULT_MODEL_PRICING)
    assert pricing_fallback.display_name == "Default Model Fallback"


def test_calculate_blended_rate():
    pricing = DEFAULT_MODEL_PRICING["gemini-3-pro"]
    # 0.70 * 1.25 + 0.20 * 5.00 + 0.10 * 0.30 = 0.875 + 1.00 + 0.03 = 1.905
    rate = calculate_blended_rate_per_million(pricing)
    assert round(rate, 3) == 1.905


def test_calculate_model_spend():
    pricing = DEFAULT_MODEL_PRICING["gemini-3-pro"]
    # 1,000,000 tokens of gemini-3-pro
    gross_spend, breakdown = calculate_model_spend(1_000_000, pricing)
    assert gross_spend == 1.905
    assert breakdown.input_spend_usd == 0.875
    assert breakdown.output_spend_usd == 1.000
    assert breakdown.cached_spend_usd == 0.030


def test_calculate_total_usage_costs_under_quota():
    tokens = {
        "gemini-3-pro": 2_000_000,  # 2M * 1.905 = $3.81
    }
    quota = 10.00
    overage = 2.00
    (
        gross_spend,
        remaining_credit,
        net_billable,
        breakdown,
        spend_by_model,
        utilization_pct,
        is_throttled,
    ) = calculate_total_usage_costs(tokens, DEFAULT_MODEL_PRICING, quota, overage)

    assert gross_spend == 3.81
    assert remaining_credit == 6.19
    assert net_billable == 0.00
    assert utilization_pct == 38.1
    assert is_throttled is False


def test_calculate_total_usage_costs_in_overage_buffer():
    tokens = {
        "gemini-3-pro": 6_000_000,  # 6M * 1.905 = $11.43
    }
    quota = 10.00
    overage = 2.00  # Hard limit is $12.00
    (
        gross_spend,
        remaining_credit,
        net_billable,
        breakdown,
        spend_by_model,
        utilization_pct,
        is_throttled,
    ) = calculate_total_usage_costs(tokens, DEFAULT_MODEL_PRICING, quota, overage)

    assert gross_spend == 11.43
    assert remaining_credit == 0.00
    assert net_billable == 1.43
    assert utilization_pct == 114.3
    assert is_throttled is False  # $11.43 < $12.00


def test_calculate_total_usage_costs_hard_breach():
    tokens = {
        "gemini-3-pro": 7_000_000,  # 7M * 1.905 = $13.335 -> $13.34
    }
    quota = 10.00
    overage = 2.00  # Hard limit is $12.00
    (
        gross_spend,
        remaining_credit,
        net_billable,
        breakdown,
        spend_by_model,
        utilization_pct,
        is_throttled,
    ) = calculate_total_usage_costs(tokens, DEFAULT_MODEL_PRICING, quota, overage)

    assert gross_spend >= 13.33
    assert remaining_credit == 0.00
    assert net_billable >= 3.33
    assert is_throttled is True  # $13.34 >= $12.00


def test_match_gemini_4_argon_and_claude_models():
    # Gemini 4 Argon (direct, variant, and full Vertex path with project digits + '-prod')
    pricing_argon = match_model_pricing("gemini-4-argon", DEFAULT_MODEL_PRICING)
    assert pricing_argon.display_name == "Gemini 4 Argon (High / Medium / Low)"

    pricing_argon_endpoint = match_model_pricing(
        "projects/315513887778-prod/locations/global/publishers/google/models/gemini-4-argon-high",
        DEFAULT_MODEL_PRICING,
    )
    assert pricing_argon_endpoint.display_name == "Gemini 4 Argon (High / Medium / Low)"

    # Anthropic Claude Sonnet (5.5, 4.6, 3.7, and Vertex endpoints)
    pricing_sonnet = match_model_pricing("claude-sonnet-5-5-medium", DEFAULT_MODEL_PRICING)
    assert pricing_sonnet.display_name == "Anthropic Claude Sonnet 5.5 / 4.6"
    pricing_sonnet_46 = match_model_pricing("claude-sonnet-4-6", DEFAULT_MODEL_PRICING)
    assert pricing_sonnet_46.display_name == "Anthropic Claude Sonnet 5.5 / 4.6"
    pricing_sonnet_legacy = match_model_pricing("claude-3-7-sonnet@20250219", DEFAULT_MODEL_PRICING)
    assert pricing_sonnet_legacy.display_name == "Anthropic Claude Sonnet 5.5 / 4.6"

    # Anthropic Claude Opus (5.5, 4.6 thinking, and Vertex endpoints)
    pricing_opus = match_model_pricing("claude-opus-5-5-high", DEFAULT_MODEL_PRICING)
    assert pricing_opus.display_name == "Anthropic Claude Opus 5.5 / 4.6"
    pricing_opus_46 = match_model_pricing("claude-opus-4-6-thinking", DEFAULT_MODEL_PRICING)
    assert pricing_opus_46.display_name == "Anthropic Claude Opus 5.5 / 4.6"

    # Literal dot escaping: '3x5' must NOT match '%3.5%flash%'
    non_dot_match = match_model_pricing("gemini-3x5-flash", DEFAULT_MODEL_PRICING)
    assert non_dot_match.display_name == "Default Model Fallback"


def test_calculate_blended_rate_new_models():
    # gemini-4-argon: 0.70 * 2.00 + 0.20 * 10.00 + 0.10 * 0.10 = 1.40 + 2.00 + 0.01 = 3.4100
    argon_rate = calculate_blended_rate_per_million(DEFAULT_MODEL_PRICING["gemini-4-argon"])
    assert round(argon_rate, 4) == 3.4100

    # claude-opus-5-5: 0.70 * 4.00 + 0.20 * 20.00 + 0.10 * 0.20 = 2.80 + 4.00 + 0.02 = 6.8200
    opus_rate = calculate_blended_rate_per_million(DEFAULT_MODEL_PRICING["claude-opus-5-5"])
    assert round(opus_rate, 4) == 6.8200

    # claude-sonnet-5-5: 0.70 * 2.00 + 0.20 * 10.00 + 0.10 * 0.20 = 1.40 + 2.00 + 0.02 = 3.4200
    sonnet_rate = calculate_blended_rate_per_million(DEFAULT_MODEL_PRICING["claude-sonnet-5-5"])
    assert round(sonnet_rate, 4) == 3.4200

