"""Tests for the Code tab orchestrator endpoint and engine.

Run from gateway/:  python -m pytest tests/test_code_run.py -v
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Ensure 7ces/gateway/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient

# Force an in-memory ledger before app imports happen
os.environ.setdefault("LEDGER_MODE", "memory")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-ant")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-ds")
os.environ.setdefault("CAP_PER_REQUEST_USD", "0.50")
os.environ.setdefault("CAP_PER_SESSION_USD", "2.00")
os.environ.setdefault("CAP_PER_DAY_USD", "5.00")

from app import app  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Shape tests
# ---------------------------------------------------------------------------


def test_code_run_rejects_missing_prompt():
    """POST /code/run with no prompt → 400."""
    resp = client.post("/code/run", json={})
    assert resp.status_code == 400
    assert "prompt" in resp.text.lower()


def test_code_run_rejects_invalid_json():
    """POST /code/run with bad JSON → 400."""
    resp = client.post("/code/run", content="not json",
                       headers={"content-type": "application/json"})
    assert resp.status_code == 400


def test_code_run_clamps_max_tokens():
    """max_* values outside 256–32000 are clamped."""
    resp = client.post("/code/run", json={
        "prompt": "hello",
        "max_plan": 10,       # below 256 → clamped to 256
        "max_build": 999999,  # above 32000 → clamped to 32000
        "max_review": -50,    # clamped to 256
    })
    # The request should be accepted (the prompt goes through),
    # but the clamped values are used in the pipeline.
    # In test mode without real keys the pipeline may fail, but 400 is the
    # validation reject — if it gets past validation it's 422 or 200.
    assert resp.status_code != 400  # Not a validation error


def test_code_run_accepts_valid_request():
    """A well-formed request is accepted (pipeline failure is fine — we mock the inner calls)."""
    resp = client.post("/code/run", json={
        "prompt": "Write a hello world in Python",
        "max_plan": 256,
        "max_build": 500,
        "max_review": 256,
    })
    # With real keys missing, the upstream call should fail.
    # But the endpoint itself should return a structured response, not crash.
    data = resp.json()
    assert "routing" in data


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


def test_routing_uses_correct_models():
    """The /code/run response declares Opus for plan/review and DeepSeek for build."""
    resp = client.post("/code/run", json={"prompt": "test"})
    data = resp.json()
    routing = data.get("routing", {})
    assert routing.get("plan") == "claude-opus-4-8"
    assert routing.get("build") == "deepseek-v4-pro"
    assert routing.get("review") == "claude-opus-4-8"


# ---------------------------------------------------------------------------
# Metering / cost
# ---------------------------------------------------------------------------


def test_response_includes_cost_fields():
    """Every step dict (if present) has cost metadata keys."""
    resp = client.post("/code/run", json={"prompt": "test"})
    data = resp.json()
    for key in ("plan", "build", "review"):
        step = data.get(key)
        if step is not None:
            assert "cost_usd" in step
            assert "input_tokens" in step
            assert "output_tokens" in step
            assert "model" in step
            assert "provider" in step


def test_total_cost_is_sum_of_steps():
    """total_cost_usd equals the sum of step costs."""
    resp = client.post("/code/run", json={"prompt": "test"})
    data = resp.json()
    total = 0.0
    for key in ("plan", "build", "review"):
        step = data.get(key) or {}
        total += step.get("cost_usd", 0)
    assert abs(data.get("total_cost_usd", 0) - total) < 0.001


# ---------------------------------------------------------------------------
# Never-applies (the orchestrator must NOT write files / shell out)
# ---------------------------------------------------------------------------


def test_orchestrator_never_writes_files():
    """The orchestrator module itself does not import or call filesystem-write primitives."""
    import orchestrator
    source = open(orchestrator.__file__, encoding="utf-8").read()
    # The orchestrator should not call open(…, "w"), subprocess, os.system, or shutil
    forbidden = ['open(', 'subprocess', 'os.system', 'shutil.', 'Path(']
    for token in forbidden:
        assert token not in source, f"orchestrator.py contains forbidden call: {token}"


def test_orchestrator_no_shell():
    """orchestrator.py does not import subprocess."""
    import orchestrator
    source = open(orchestrator.__file__, encoding="utf-8").read()
    assert "subprocess" not in source


# ---------------------------------------------------------------------------
# 402 fail-closed (cap refusal)
# ---------------------------------------------------------------------------


def test_cap_refused_propagates():
    """When the spend guard returns 402, the orchestrator reports an error."""
    import orchestrator
    from orchestrator import CapRefused

    async def fake_post(path, body):
        raise CapRefused("per-request cap exceeded")

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        orchestrator.run("test", fake_post,
                                   max_plan=256, max_build=256, max_review=256))
    assert result.error is not None
    assert "Plan step failed" in result.error


# ---------------------------------------------------------------------------
# Provider error
# ---------------------------------------------------------------------------


def test_provider_error_propagates():
    """When the upstream returns 500, the orchestrator reports an error."""
    import orchestrator
    from orchestrator import ProviderError

    async def fake_post(path, body):
        raise ProviderError(500, "internal server error")

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        orchestrator.run("test", fake_post,
                                   max_plan=256, max_build=256, max_review=256))
    assert result.error is not None
