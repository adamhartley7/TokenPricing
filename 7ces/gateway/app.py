"""
7CE's spend-guard gateway — HTTP surface.

LibreChat (and later the Code/Cowork tabs) point their provider baseURL at this gateway:
  * Anthropic (Claude) :  POST /anthropic/v1/messages
  * DeepSeek           :  POST /deepseek/v1/chat/completions

For every metered call the gateway:
  1. bounds output (injects a default max_tokens if absent),
  2. estimates input tokens (Claude count_tokens / DeepSeek tokenizer-or-heuristic),
  3. ENFORCES the spend caps BEFORE forwarding — refusing with HTTP 402 if over,
  4. forwards (plain or SSE-streamed) with the gateway's OWN key (client auth is stripped),
  5. meters the ACTUAL cost from the response usage into the ledger (the running cost meter).

Other subpaths (e.g. /v1/models, /v1/messages/count_tokens) are authenticated and passed through
without metering. Run with:  uvicorn app:app --host 127.0.0.1 --port 8787
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

import pricing
import tokencount
from config import config
from ledger import SESSION_ID, Ledger
from providers import AnthropicProvider, DeepSeekProvider
from providers.base import coerce_per_request_cap
from spendguard import SpendGuard

log = logging.getLogger("7ces.gateway")
logging.basicConfig(level=logging.INFO, format="%(message)s")

GATEWAY_DIR = Path(__file__).resolve().parent

app = FastAPI(title="7CE's spend-guard gateway", version="0.1.0")


def init_state(ledger: Ledger | None = None) -> None:
    """Initialise (or reset, for tests) the gateway's ledger, guard and provider registry."""
    led = ledger or Ledger()
    app.state.ledger = led
    app.state.guard = SpendGuard(led)
    app.state.providers = {
        "anthropic": AnthropicProvider(config.anthropic_base, config.anthropic_key),
        "deepseek": DeepSeekProvider(config.deepseek_base, config.deepseek_key),
    }


init_state()


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------
def _split_sse(buffer: str) -> tuple[list[str], str]:
    """Split a text buffer into complete lines, returning (lines, remainder)."""
    if "\n" not in buffer:
        return [], buffer
    *complete, remainder = buffer.split("\n")
    return complete, remainder


def _parse_sse_data(line: str) -> dict | None:
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[len("data:"):].strip()
    if not data or data == "[DONE]":
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Metering
# ---------------------------------------------------------------------------
def _meter(provider_name: str, model: str, usage: dict | None, session_id: str, note: str) -> float:
    ledger = app.state.ledger
    try:
        cost = pricing.actual_usd(model, usage) if usage else 0.0
    except pricing.PricingError:
        cost = 0.0
    in_t, out_t = pricing.tokens_from_usage(usage) if usage else (0, 0)
    ledger.record(
        session_id=session_id, provider=provider_name, model=model, cost_usd=cost,
        input_tokens=in_t, output_tokens=out_t, capped=False, note=note,
    )
    log.info(
        "[7CE's] %s %s in=%d out=%d cost=$%.5f  session=$%.4f/%.2f  day=$%.4f/%.2f",
        provider_name, model, in_t, out_t, cost,
        ledger.session_total(session_id), config.cap_per_session,
        ledger.day_total(), config.cap_per_day,
    )
    return cost


# ---------------------------------------------------------------------------
# Core metered handler
# ---------------------------------------------------------------------------
async def _handle(provider_key: str, subpath: str, request: Request) -> JSONResponse | StreamingResponse:
    provider = app.state.providers[provider_key]
    guard: SpendGuard = app.state.guard

    raw = await request.body()
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": {"type": "bad_request", "message": "invalid JSON body"}}, status_code=400)

    session_id = request.headers.get("x-7ces-session", SESSION_ID)
    prepared, model, max_tokens, is_stream = provider.prepare(body, config.default_max_tokens)

    # --- pre-flight estimate + cap enforcement (BEFORE any forward) ---------
    input_tokens = await tokencount.estimate_input_tokens(provider_key, prepared)
    decision = guard.check(
        provider=provider_key, model=model or "", input_tokens=input_tokens,
        max_output_tokens=max_tokens, session_id=session_id,
        per_request_cap_override=coerce_per_request_cap(request.headers),
    )
    if not decision.allowed:
        app.state.ledger.record(
            session_id=session_id, provider=provider_key, model=model or "unknown",
            cost_usd=0.0, capped=True, note=decision.reason,
        )
        log.info("[7CE's] REFUSED %s %s — %s", provider_key, model, decision.reason)
        return JSONResponse(decision.as_error_payload(), status_code=402)

    # The guard placed a worst-case hold; it MUST be released once the call settles, on every path.
    reserved = decision.worst_case_usd
    _released = {"done": False}

    def _release():
        if not _released["done"]:
            _released["done"] = True
            guard.release(session_id, reserved)

    headers = provider.auth_headers(dict(request.headers))
    headers["accept-encoding"] = "identity"  # plain bytes so we can tee the SSE stream
    url = provider.upstream_url(subpath)

    if not is_stream:
        try:
            async with httpx.AsyncClient(timeout=config.upstream_timeout) as client:
                up = await client.post(url, json=prepared, headers=headers)
            try:
                payload = up.json()
            except json.JSONDecodeError:
                return JSONResponse(
                    {"error": {"type": "upstream_error", "message": up.text[:500]}},
                    status_code=up.status_code,
                )
            if up.status_code < 400:
                _meter(provider_key, pricing.resolve(model), provider.usage_from_json(payload),
                       session_id, note=subpath)
            return JSONResponse(payload, status_code=up.status_code)
        finally:
            _release()

    # --- streaming: pass raw bytes through while teeing usage out -----------
    client = httpx.AsyncClient(timeout=config.upstream_timeout)
    try:
        req = client.build_request("POST", url, json=prepared, headers=headers)
        up = await client.send(req, stream=True)
    except BaseException:
        await client.aclose()
        _release()
        raise

    async def streamer():
        acc = provider.new_stream_accumulator()
        buffer = ""
        try:
            async for chunk in up.aiter_raw():
                yield chunk
                buffer += chunk.decode("utf-8", "ignore")
                lines, buffer = _split_sse(buffer)
                for line in lines:
                    obj = _parse_sse_data(line)
                    if obj is not None:
                        acc.feed(obj)
        finally:
            await up.aclose()
            await client.aclose()
            if up.status_code < 400:
                _meter(provider_key, pricing.resolve(model), acc.result(),
                       session_id, note=f"{subpath} (stream)")
            _release()

    media = up.headers.get("content-type", "text/event-stream")
    return StreamingResponse(streamer(), status_code=up.status_code, media_type=media)


# ---------------------------------------------------------------------------
# Passthrough — ALLOW-LIST ONLY. Anything not listed is rejected, because forwarding it would
# inject the gateway's key into an un-capped, un-metered call (e.g. the billable /v1/complete or
# /v1/completions endpoints). Only known NON-billable auxiliary paths are passed through.
# ---------------------------------------------------------------------------
_PASSTHROUGH_ALLOW = {
    "anthropic": {"v1/models", "v1/messages/count_tokens"},
    "deepseek": {"v1/models", "user/balance"},
}


async def _passthrough(provider_key: str, subpath: str, request: Request) -> JSONResponse:
    norm = subpath.strip("/")
    if norm not in _PASSTHROUGH_ALLOW.get(provider_key, set()):
        return JSONResponse(
            {"error": {
                "type": "blocked",
                "message": (
                    f"/{provider_key}/{subpath} is not allowed through the gateway. Only the "
                    "metered, cap-checked completion endpoints and a few non-billable paths "
                    "(models list, count_tokens, balance) are permitted — this prevents bypassing "
                    "the spend cap."
                ),
            }},
            status_code=403,
        )
    provider = app.state.providers[provider_key]
    headers = provider.auth_headers(dict(request.headers))
    headers["accept-encoding"] = "identity"
    url = provider.upstream_url(subpath)
    raw = await request.body()
    async with httpx.AsyncClient(timeout=60.0) as client:
        up = await client.request(request.method, url, content=raw or None, headers=headers)
    try:
        return JSONResponse(up.json(), status_code=up.status_code)
    except json.JSONDecodeError:
        return JSONResponse({"raw": up.text[:2000]}, status_code=up.status_code)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/anthropic/v1/messages")
async def anthropic_messages(request: Request):
    return await _handle("anthropic", "v1/messages", request)


@app.post("/deepseek/v1/chat/completions")
async def deepseek_chat(request: Request):
    return await _handle("deepseek", "v1/chat/completions", request)


@app.api_route("/anthropic/{subpath:path}", methods=["GET", "POST"])
async def anthropic_passthrough(subpath: str, request: Request):
    return await _passthrough("anthropic", subpath, request)


@app.api_route("/deepseek/{subpath:path}", methods=["GET", "POST"])
async def deepseek_passthrough(subpath: str, request: Request):
    return await _passthrough("deepseek", subpath, request)


@app.get("/meter")
async def meter(request: Request):
    session_id = request.headers.get("x-7ces-session", SESSION_ID)
    return JSONResponse(app.state.ledger.meter_snapshot(session_id))


@app.get("/health")
async def health():
    return {
        "ok": True,
        "session_id": SESSION_ID,
        "providers": {
            "anthropic": bool(config.anthropic_key),
            "deepseek": bool(config.deepseek_key),
        },
        "caps": config.caps(),
    }


@app.get("/", response_class=HTMLResponse)
async def meter_page():
    page = GATEWAY_DIR / "meter.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>7CE's gateway</h1><p>See <a href='/meter'>/meter</a>.</p>")


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    """A tiny no-Docker chat UI that talks straight to the gateway (same-origin, so no CORS)."""
    page = GATEWAY_DIR / "chat.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>7CE's chat</h1><p>chat.html is missing.</p>")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=config.host, port=config.port, reload=False)
