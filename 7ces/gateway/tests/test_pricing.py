"""Pricing math — must match REPORT.md section 2 figures exactly."""
import math

import pytest

import pricing


def test_resolve_aliases():
    assert pricing.resolve("opus") == "claude-opus-4-8"
    assert pricing.resolve("deepseek-chat") == "deepseek-v4-pro"
    assert pricing.resolve("deepseek-v4-flash") == "deepseek-v4-flash"
    # tolerant prefix match
    assert pricing.resolve("claude-opus-4-8-20260101") == "claude-opus-4-8"


def test_unknown_model_raises():
    with pytest.raises(pricing.PricingError):
        pricing.resolve("gpt-5.5")
    with pytest.raises(pricing.PricingError):
        pricing.resolve(None)


def test_worst_case_opus():
    # (1000*5 + 1000*25) / 1e6 = 0.030
    assert math.isclose(pricing.worst_case_usd("claude-opus-4-8", 1000, 1000), 0.030, rel_tol=1e-9)


def test_worst_case_deepseek_pro():
    # (1000*0.435 + 1000*0.87) / 1e6 = 0.001305
    assert math.isclose(pricing.worst_case_usd("deepseek-v4-pro", 1000, 1000), 0.001305, rel_tol=1e-9)


def test_actual_anthropic_usage():
    # input 1000 @ $5, output 500 @ $25 = (5000 + 12500)/1e6 = 0.0175
    usage = {"input_tokens": 1000, "output_tokens": 500}
    assert math.isclose(pricing.actual_usd("claude-opus-4-8", usage), 0.0175, rel_tol=1e-9)


def test_actual_anthropic_with_cache():
    # fresh 1000@5 + cache_read 2000@0.5 + cache_write 500@6.25 + out 100@25
    usage = {
        "input_tokens": 1000, "output_tokens": 100,
        "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 500,
    }
    expected = (1000 * 5 + 2000 * 0.5 + 500 * 6.25 + 100 * 25) / 1e6
    assert math.isclose(pricing.actual_usd("claude-opus-4-8", usage), expected, rel_tol=1e-9)


def test_actual_openai_usage_with_cache():
    # prompt 1000 (200 cached) -> 800 fresh @0.435 + 200 cached @0.003625 + completion 500 @0.87
    usage = {
        "prompt_tokens": 1000, "completion_tokens": 500,
        "prompt_tokens_details": {"cached_tokens": 200},
    }
    expected = (800 * 0.435 + 200 * 0.003625 + 500 * 0.87) / 1e6
    assert math.isclose(pricing.actual_usd("deepseek-v4-pro", usage), expected, rel_tol=1e-9)


def test_tokens_from_usage():
    assert pricing.tokens_from_usage({"input_tokens": 10, "output_tokens": 5}) == (10, 5)
    assert pricing.tokens_from_usage({"prompt_tokens": 7, "completion_tokens": 3}) == (7, 3)
    assert pricing.tokens_from_usage(None) == (0, 0)


def test_catalog():
    cat = pricing.catalog()
    ids = {m["id"] for m in cat}
    assert "deepseek-v4-flash" in ids and "claude-opus-4-8" in ids
    flash = next(m for m in cat if m["id"] == "deepseek-v4-flash")
    assert flash["provider"] == "deepseek" and flash["output"] == 0.28
    assert flash["confirmed"] is False


def test_report_md_anchor_values():
    """Spot-check the headline per-1M rates against REPORT.md."""
    assert pricing.rates("claude-opus-4-8")["input"] == 5.0
    assert pricing.rates("claude-opus-4-8")["output"] == 25.0
    assert pricing.rates("deepseek-v4-pro")["input"] == 0.435
    assert pricing.rates("deepseek-v4-flash")["output"] == 0.28
