"""
Pricing math for the gateway. Loads pricing.json (the single source of cost truth, reused from
REPORT.md) and exposes:

  * resolve(model)            -> canonical model id (via aliases)
  * rates(model)              -> dict of per-1M rates
  * worst_case_usd(...)       -> PRE-call upper bound: input cost (cache-naive) + max_tokens*output
  * actual_usd(model, usage)  -> POST-call true cost from a provider 'usage' object

worst_case is deliberately cache-naive (assumes every input token is billed at full rate and the
model emits the full max_tokens) so it is a genuine upper bound for the spend cap.
"""
from __future__ import annotations

import json
from pathlib import Path

_PRICING_PATH = Path(__file__).resolve().parent / "pricing.json"


class PricingError(ValueError):
    """Raised when a model is unknown and cannot be priced (so we can fail closed)."""


def _load() -> dict:
    with open(_PRICING_PATH, encoding="utf-8") as fh:
        return json.load(fh)


_DATA = _load()
_PER = _DATA["per_tokens"]  # 1_000_000


def reload() -> None:
    """Re-read pricing.json (used by tests)."""
    global _DATA, _PER
    _DATA = _load()
    _PER = _DATA["per_tokens"]


def resolve(model: str | None) -> str:
    """Map a possibly-aliased model id to its canonical id, or raise PricingError."""
    if not model:
        raise PricingError("no model supplied")
    aliases = _DATA.get("aliases", {})
    if model in _DATA["models"]:
        return model
    if model in aliases:
        return aliases[model]
    # tolerant prefix match (e.g. 'claude-opus-4-8-20260101' -> opus)
    for alias, canonical in aliases.items():
        if model.startswith(alias):
            return canonical
    raise PricingError(f"unknown model '{model}' — add it to pricing.json")


def rates(model: str) -> dict:
    return _DATA["models"][resolve(model)]


def is_confirmed(model: str) -> bool:
    return bool(rates(model).get("confirmed", False))


def worst_case_usd(model: str, input_tokens: int, max_output_tokens: int) -> float:
    """Upper-bound cost of a request BEFORE it runs. Cache-naive on input."""
    r = rates(model)
    return (input_tokens * r["input"] + max_output_tokens * r["output"]) / _PER


def actual_usd(model: str, usage: dict) -> float:
    """
    True cost from a provider 'usage' object. Handles both shapes:
      * Anthropic: input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens
      * OpenAI/DeepSeek: prompt_tokens, completion_tokens, prompt_tokens_details.cached_tokens
    Cached input is billed at cache_read; freshly-written cache (Anthropic) at cache_write_5m.
    """
    r = rates(model)
    if usage is None:
        return 0.0

    # Anthropic-style
    if "input_tokens" in usage or "output_tokens" in usage:
        fresh_in = usage.get("input_tokens", 0) or 0
        out = usage.get("output_tokens", 0) or 0
        cache_write = usage.get("cache_creation_input_tokens", 0) or 0
        cache_read = usage.get("cache_read_input_tokens", 0) or 0
        cost = (
            fresh_in * r["input"]
            + out * r["output"]
            + cache_write * r.get("cache_write_5m", r["input"])
            + cache_read * r.get("cache_read", r["input"])
        )
        return cost / _PER

    # OpenAI/DeepSeek-style
    prompt = usage.get("prompt_tokens", 0) or 0
    completion = usage.get("completion_tokens", 0) or 0
    cached = 0
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        cached = details.get("cached_tokens", 0) or 0
    fresh_prompt = max(prompt - cached, 0)
    cost = (
        fresh_prompt * r["input"]
        + cached * r.get("cache_read", r["input"])
        + completion * r["output"]
    )
    return cost / _PER


def catalog() -> list[dict]:
    """Public model list for the UI: id, provider, per-1M prices, and the confirmed flag."""
    return [
        {
            "id": mid,
            "provider": m["provider"],
            "input": m["input"],
            "output": m["output"],
            "confirmed": bool(m.get("confirmed", False)),
        }
        for mid, m in _DATA["models"].items()
    ]


def tokens_from_usage(usage: dict) -> tuple[int, int]:
    """Return (input_tokens, output_tokens) from either usage shape, for the ledger."""
    if not usage:
        return 0, 0
    if "input_tokens" in usage or "output_tokens" in usage:
        in_t = (usage.get("input_tokens", 0) or 0) + (usage.get("cache_read_input_tokens", 0) or 0) + (
            usage.get("cache_creation_input_tokens", 0) or 0
        )
        return in_t, (usage.get("output_tokens", 0) or 0)
    return (usage.get("prompt_tokens", 0) or 0), (usage.get("completion_tokens", 0) or 0)
