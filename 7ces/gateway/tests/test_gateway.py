"""
Gateway HTTP behaviour. The headline guarantee: an over-cap request returns 402 and the upstream
provider is NEVER contacted (fail-closed). Plus: output bounding, metering, and stream usage capture.

All upstream HTTP is faked, so these tests make no network calls and spend nothing.
"""
import json

import pytest
from fastapi.testclient import TestClient

import app as gw
from ledger import fresh_test_ledger


# ---------------------------------------------------------------------------
# Fakes for httpx
# ---------------------------------------------------------------------------
class FakeResp:
    def __init__(self, payload=None, status=200, content_type="application/json"):
        self._payload = payload if payload is not None else {}
        self.status_code = status
        self.text = json.dumps(self._payload)
        self.headers = {"content-type": content_type}

    def json(self):
        return self._payload


class FakeStreamResp:
    def __init__(self, chunks, status=200):
        self._chunks = chunks
        self.status_code = status
        self.headers = {"content-type": "text/event-stream"}

    async def aiter_raw(self):
        for c in self._chunks:
            yield c

    async def aclose(self):
        pass


class FakeClient:
    forwarded = {"count": 0, "last_json": None}
    nonstream_payload = {"id": "x", "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    stream_chunks = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        FakeClient.forwarded["count"] += 1
        FakeClient.forwarded["last_json"] = json
        return FakeResp(FakeClient.nonstream_payload)

    def build_request(self, method, url, json=None, headers=None):
        FakeClient.forwarded["count"] += 1
        FakeClient.forwarded["last_json"] = json
        return {"m": method, "u": url}

    async def send(self, req, stream=False):
        return FakeStreamResp(FakeClient.stream_chunks)

    async def request(self, method, url, content=None, headers=None):
        FakeClient.forwarded["count"] += 1
        return FakeResp({"ok": True})

    async def aclose(self):
        pass


async def _fake_estimate(provider, body):
    return 100


@pytest.fixture
def client(monkeypatch):
    FakeClient.forwarded = {"count": 0, "last_json": None}
    FakeClient.nonstream_payload = {"id": "x", "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    FakeClient.stream_chunks = []
    monkeypatch.setattr(gw.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(gw.tokencount, "estimate_input_tokens", _fake_estimate)
    gw.init_state(fresh_test_ledger())
    return TestClient(gw.app)


# ---------------------------------------------------------------------------
# THE non-negotiable: over-cap refused before any forward
# ---------------------------------------------------------------------------
def test_over_cap_refused_before_forward(client, monkeypatch):
    monkeypatch.setattr(gw.config, "cap_per_request", 0.0001)
    r = client.post(
        "/anthropic/v1/messages",
        json={"model": "claude-opus-4-8", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 402
    body = r.json()
    assert body["error"]["type"] == "spend_cap_exceeded"
    # Upstream must NEVER have been contacted.
    assert FakeClient.forwarded["count"] == 0
    # The refusal is logged as a capped row that does NOT count as spend.
    meter = client.get("/meter").json()
    assert meter["totals"]["session_usd"] == 0.0


def test_within_cap_nonstream_meters(client):
    r = client.post(
        "/deepseek/v1/chat/completions",
        json={"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hi"}],
              "max_tokens": 100},
    )
    assert r.status_code == 200
    assert FakeClient.forwarded["count"] == 1
    meter = client.get("/meter").json()
    expected = (100 * 0.14 + 50 * 0.28) / 1e6  # prompt 100 @in, completion 50 @out
    assert abs(meter["totals"]["session_usd"] - expected) < 1e-12
    assert meter["by_provider"]["deepseek"]["calls"] == 1


def test_default_max_tokens_injected(client):
    client.post(
        "/deepseek/v1/chat/completions",
        json={"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert FakeClient.forwarded["last_json"]["max_tokens"] == gw.config.default_max_tokens


def test_streaming_usage_captured(client):
    FakeClient.stream_chunks = [
        b'data: {"choices":[{"delta":{"content":"hi"}}],"usage":null}\n\n',
        b'data: {"choices":[],"usage":{"prompt_tokens":100,"completion_tokens":50,"total_tokens":150}}\n\n',
        b"data: [DONE]\n\n",
    ]
    with client.stream(
        "POST",
        "/deepseek/v1/chat/completions",
        json={"model": "deepseek-v4-flash", "stream": True,
              "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100},
    ) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes())
    assert b"[DONE]" in body
    meter = client.get("/meter").json()
    expected = (100 * 0.14 + 50 * 0.28) / 1e6
    assert abs(meter["totals"]["session_usd"] - expected) < 1e-12


def test_stream_options_include_usage_injected(client):
    FakeClient.stream_chunks = [b"data: [DONE]\n\n"]
    with client.stream(
        "POST",
        "/deepseek/v1/chat/completions",
        json={"model": "deepseek-v4-flash", "stream": True,
              "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100},
    ) as r:
        list(r.iter_bytes())
    assert FakeClient.forwarded["last_json"]["stream_options"]["include_usage"] is True


def test_negative_max_tokens_is_bounded(client):
    # A negative max_tokens must NOT slip past the default (it would deflate the worst-case).
    client.post(
        "/deepseek/v1/chat/completions",
        json={"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hi"}],
              "max_tokens": -5},
    )
    assert FakeClient.forwarded["last_json"]["max_tokens"] == gw.config.default_max_tokens


def test_passthrough_allows_models(client):
    r = client.get("/deepseek/v1/models")
    assert r.status_code == 200
    assert FakeClient.forwarded["count"] == 1


def test_passthrough_blocks_billable_endpoint(client):
    # /v1/completions is a billable endpoint NOT on the allow-list — must be refused, not forwarded.
    r = client.post("/deepseek/v1/completions", json={"model": "deepseek-v4-pro", "prompt": "hi"})
    assert r.status_code == 403
    assert r.json()["error"]["type"] == "blocked"
    assert FakeClient.forwarded["count"] == 0


def test_health(client):
    h = client.get("/health").json()
    assert h["ok"] is True
    assert "anthropic" in h["providers"] and "deepseek" in h["providers"]
