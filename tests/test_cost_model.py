"""Unit tests for cost modeling, hinge points, and credit mechanics."""

from unittest.mock import MagicMock, patch

from google.cloud import firestore

from app.core.cost_model import (
    calculate_blended_rate_per_million,
    calculate_model_spend,
    calculate_total_usage_costs,
    match_model_pricing,
)
from app.db.firestore_client import FirestoreDatabase
from app.db.models import DEFAULT_MODEL_PRICING, DEPRECATED_MODEL_KEYS, AppConfig


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

    # Gemini 4 Carbon (Frontier Planner)
    pricing_carbon = match_model_pricing("gemini-4-carbon", DEFAULT_MODEL_PRICING)
    assert pricing_carbon.display_name == "Gemini 4 Carbon (Frontier Planner)"

    pricing_carbon_endpoint = match_model_pricing(
        "projects/315513887778-prod/locations/global/publishers/google/models/gemini-4-carbon-high",
        DEFAULT_MODEL_PRICING,
    )
    assert pricing_carbon_endpoint.display_name == "Gemini 4 Carbon (Frontier Planner)"

    # Gemini 4 Hydrogen (Fast Execution)
    pricing_hydrogen = match_model_pricing("gemini-4-hydrogen", DEFAULT_MODEL_PRICING)
    assert pricing_hydrogen.display_name == "Gemini 4 Hydrogen (Fast Execution)"

    pricing_hydrogen_endpoint = match_model_pricing(
        "projects/315513887778-prod/locations/global/publishers/google/models/gemini-4-hydrogen-fast",
        DEFAULT_MODEL_PRICING,
    )
    assert pricing_hydrogen_endpoint.display_name == "Gemini 4 Hydrogen (Fast Execution)"

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

    # gemini-4-carbon: 0.70 * 2.00 + 0.20 * 10.00 + 0.10 * 0.10 = 1.40 + 2.00 + 0.01 = 3.4100
    carbon_rate = calculate_blended_rate_per_million(DEFAULT_MODEL_PRICING["gemini-4-carbon"])
    assert round(carbon_rate, 4) == 3.4100

    # gemini-4-hydrogen: 0.70 * 1.50 + 0.20 * 7.50 + 0.10 * 0.075 = 1.05 + 1.50 + 0.0075 = 2.5575
    hydrogen_rate = calculate_blended_rate_per_million(DEFAULT_MODEL_PRICING["gemini-4-hydrogen"])
    assert round(hydrogen_rate, 4) == 2.5575

    # claude-opus-5-5: 0.70 * 4.00 + 0.20 * 20.00 + 0.10 * 0.20 = 2.80 + 4.00 + 0.02 = 6.8200
    opus_rate = calculate_blended_rate_per_million(DEFAULT_MODEL_PRICING["claude-opus-5-5"])
    assert round(opus_rate, 4) == 6.8200

    # claude-sonnet-5-5: 0.70 * 2.00 + 0.20 * 10.00 + 0.10 * 0.20 = 1.40 + 2.00 + 0.02 = 3.4200
    sonnet_rate = calculate_blended_rate_per_million(DEFAULT_MODEL_PRICING["claude-sonnet-5-5"])
    assert round(sonnet_rate, 4) == 3.4200


def test_deprecated_gemini_2_5_models_removed():
    """Verify deprecated Gemini 2.5 Pro/Flash are absent from DEFAULT_MODEL_PRICING and fall back."""
    for key in ("gemini-2.5-pro", "gemini-2.5-flash"):
        assert key in DEPRECATED_MODEL_KEYS
        assert key not in DEFAULT_MODEL_PRICING
        fallback = match_model_pricing(key, DEFAULT_MODEL_PRICING)
        assert fallback.display_name == "Default Model Fallback"


def test_firestore_config_prunes_deprecated_models():
    """Verify FirestoreDatabase.get_config() and update_config() strip deprecated model keys."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "default_weekly_quota_usd": 10.0,
        "models": {
            "gemini-2.5-pro": {
                "display_name": "Gemini 2.5 Pro",
                "log_pattern": "%2.5%pro%",
                "input_price_per_million": 1.25,
                "output_price_per_million": 5.00,
                "cached_price_per_million": 0.30,
                "estimated_input_ratio": 0.70,
                "estimated_output_ratio": 0.20,
                "estimated_cached_ratio": 0.10,
            },
            "gemini-2.5-flash": {
                "display_name": "Gemini 2.5 Flash",
                "log_pattern": "%2.5%flash%",
                "input_price_per_million": 0.075,
                "output_price_per_million": 0.30,
                "cached_price_per_million": 0.01875,
                "estimated_input_ratio": 0.80,
                "estimated_output_ratio": 0.15,
                "estimated_cached_ratio": 0.05,
            },
            "gemini-4-argon": DEFAULT_MODEL_PRICING["gemini-4-argon"].model_dump(),
        },
    }

    mock_doc_ref = MagicMock()
    mock_doc_ref.get.return_value = mock_doc
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc_ref

    with patch("app.db.firestore_client.firestore.Client", return_value=mock_client):
        db = FirestoreDatabase(project_id="test-project")
        cfg = db.get_config()

        assert "gemini-2.5-pro" not in cfg.models
        assert "gemini-2.5-flash" not in cfg.models
        assert "gemini-4-argon" in cfg.models
        assert "gemini-4-carbon" in cfg.models
        assert "gemini-4-hydrogen" in cfg.models

        # Even if caller passes a config containing deprecated keys, update_config strips & deletes them
        dirty_cfg = AppConfig()
        dirty_cfg.models["gemini-2.5-pro"] = DEFAULT_MODEL_PRICING["default_fallback"]
        dirty_cfg.models["gemini-2.5-flash"] = DEFAULT_MODEL_PRICING["default_fallback"]
        saved = db.update_config(dirty_cfg)

        assert "gemini-2.5-pro" not in saved.models
        assert "gemini-2.5-flash" not in saved.models
        set_call_args = mock_doc_ref.set.call_args
        payload = set_call_args.args[0]
        assert payload["models"]["gemini-2.5-pro"] is firestore.DELETE_FIELD
        assert payload["models"]["gemini-2.5-flash"] is firestore.DELETE_FIELD

