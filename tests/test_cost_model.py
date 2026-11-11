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
    assert pricing.display_name == "Gemini 3.1 Pro"

    pricing_flash = match_model_pricing("models/gemini-3.6-flash-preview", DEFAULT_MODEL_PRICING)
    assert pricing_flash.display_name == "Gemini 3.6 Flash"

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

    # Literal dot escaping: '3x8' must NOT match '%3.8%flash%'
    non_dot_match = match_model_pricing("gemini-3x8-flash", DEFAULT_MODEL_PRICING)
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


def test_deprecated_models_removed_and_fallback():
    from app.db.models import DEPRECATED_MODEL_KEYS

    assert DEPRECATED_MODEL_KEYS == {"gemini-2.5-pro", "gemini-2.5-flash", "gemini-3.5-flash"}

    for dep_key in ("gemini-2.5-pro", "gemini-2.5-flash", "gemini-3.5-flash"):
        assert dep_key not in DEFAULT_MODEL_PRICING
        fallback = match_model_pricing(dep_key, DEFAULT_MODEL_PRICING)
        assert fallback.display_name == "Default Model Fallback"


def test_active_models_present_and_matched():
    assert "gemini-3.7-flash" in DEFAULT_MODEL_PRICING
    assert "gemini-3.6-flash" in DEFAULT_MODEL_PRICING
    assert "gemini-3.8-flash" in DEFAULT_MODEL_PRICING
    assert "gemini-3-pro" in DEFAULT_MODEL_PRICING
    assert "gemini-4-argon" in DEFAULT_MODEL_PRICING

    assert DEFAULT_MODEL_PRICING["gemini-3.7-flash"].display_name == "Gemini 3.7 Flash"
    assert DEFAULT_MODEL_PRICING["gemini-3.6-flash"].display_name == "Gemini 3.6 Flash"
    assert DEFAULT_MODEL_PRICING["gemini-3-pro"].display_name == "Gemini 3.1 Pro"

    # Match test for gemini-3.7-flash variants
    p_37 = match_model_pricing("gemini-3.7-flash-medium", DEFAULT_MODEL_PRICING)
    assert p_37.display_name == "Gemini 3.7 Flash"

    p_37_vertex = match_model_pricing(
        "projects/12345/locations/global/publishers/google/models/gemini-3.7-flash-high",
        DEFAULT_MODEL_PRICING,
    )
    assert p_37_vertex.display_name == "Gemini 3.7 Flash"


def test_firestore_get_config_prunes_deprecated_models():
    from unittest.mock import MagicMock, patch
    from app.db.firestore_client import FirestoreDatabase

    with patch("app.db.firestore_client.firestore.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "doc_id": "app_config",
            "models": {
                "gemini-3-pro": DEFAULT_MODEL_PRICING["gemini-3-pro"].model_dump(),
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
                "gemini-3.5-flash": {
                    "display_name": "Gemini 3.5 Flash",
                    "log_pattern": "%3.5%flash%",
                    "input_price_per_million": 0.15,
                    "output_price_per_million": 0.60,
                    "cached_price_per_million": 0.0375,
                    "estimated_input_ratio": 0.75,
                    "estimated_output_ratio": 0.20,
                    "estimated_cached_ratio": 0.05,
                },
            },
        }
        mock_doc_ref.get.return_value = mock_doc
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = FirestoreDatabase(project_id="test-proj")
        cfg = db.get_config()

        assert "gemini-2.5-pro" not in cfg.models
        assert "gemini-2.5-flash" not in cfg.models
        assert "gemini-3.5-flash" not in cfg.models
        assert "gemini-3-pro" in cfg.models
        assert "gemini-3.7-flash" in cfg.models

        # Verify Firestore document was updated to persist the pruned models map without merge=True
        mock_doc_ref.set.assert_called_once()
        set_args, set_kwargs = mock_doc_ref.set.call_args
        assert set_kwargs == {}
        assert "gemini-2.5-pro" not in set_args[0]["models"]
        assert "gemini-2.5-flash" not in set_args[0]["models"]
        assert "gemini-3.5-flash" not in set_args[0]["models"]


