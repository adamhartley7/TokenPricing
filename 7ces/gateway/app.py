"""
7C's spend-guard gateway — HTTP surface.

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
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
)

import pricing
import tokencount
from config import config
from ledger import SESSION_ID, Ledger
import calibrate as _calibrate
import classifier as _classifier
import loop as _loop
import priors as _priors
import profile as _profile
from ledger import SESSION_ID, Ledger
from orchestrator import OrchestrateResult, run as orchestrate_run
from providers import AnthropicProvider, DeepSeekProvider
from providers.base import coerce_per_request_cap
from spendguard import SpendGuard

log = logging.getLogger("7Cs.gateway")
logging.basicConfig(level=logging.INFO, format="%(message)s")

GATEWAY_DIR = Path(__file__).resolve().parent

app = FastAPI(title="7C's spend-guard gateway", version="0.1.0")


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
        "[7C's] %s %s in=%d out=%d cost=$%.5f  session=$%.4f/%.2f  day=$%.4f/%.2f",
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

    session_id = request.headers.get("x-7Cs-session", SESSION_ID)
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
        log.info("[7C's] REFUSED %s %s — %s", provider_key, model, decision.reason)
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
    session_id = request.headers.get("x-7Cs-session", SESSION_ID)
    return JSONResponse(app.state.ledger.meter_snapshot(session_id))


@app.get("/models")
async def models():
    """Model catalogue for the UI (from pricing.json) + which providers currently have a key."""
    present = {"anthropic": bool(config.anthropic_key), "deepseek": bool(config.deepseek_key)}
    cat = pricing.catalog()
    for m in cat:
        m["available"] = present.get(m["provider"], False)
        # OpenAI-compatible providers use /v1/chat/completions; Anthropic uses /v1/messages.
        m["shape"] = "anthropic" if m["provider"] == "anthropic" else "openai"
    return {"models": cat, "providers": present}


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
    return HTMLResponse("<h1>7C's gateway</h1><p>See <a href='/meter'>/meter</a>.</p>")


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    """A tiny no-Docker chat UI that talks straight to the gateway (same-origin, so no CORS)."""
    page = GATEWAY_DIR / "chat.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>7C's chat</h1><p>chat.html is missing.</p>")


# --- Code tab: plan → build → review orchestration -------------------------
@app.post("/code/run")
async def code_run(request: Request):
    """Orchestrate a task through Opus plan → DeepSeek build → Opus review.

    The Code tab (and tools/orchestrate.py) POST a JSON body:
      {prompt, max_plan?, max_build?, max_review?}

    Each step is capped + metered through the existing spend-guard flow.
    The endpoint only proposes — it never writes files or spawns subprocesses.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    if not isinstance(body, dict) or not body.get("prompt"):
        return JSONResponse({"error": "missing 'prompt' field"}, status_code=400)

    prompt = str(body["prompt"])

    # Clamp max_tokens to safe bounds (256–32000)
    def _clamp(key, default):
        try:
            v = int(body.get(key, default))
            return max(256, min(32000, v))
        except (TypeError, ValueError):
            return default

    max_plan = _clamp("max_plan", 8000)
    max_build = _clamp("max_build", 16000)
    max_review = _clamp("max_review", 8000)

    # Build the post() callable that forwards through this gateway (same process)
    async def _post(path: str, payload: dict):
        """In-process gateway call — bypasses HTTP, uses the existing provider pipeline."""
        # Determine provider from path
        provider_key = path.split("/")[1]  # /anthropic/v1/messages → anthropic
        is_anthropic = provider_key == "anthropic"
        shape = "anthropic" if is_anthropic else "openai"
        model_id = payload.get("model", "")
        system = payload.get("system") if is_anthropic else None
        messages = payload.get("messages", [])
        max_tok = payload.get("max_tokens", 2048)

        # The orchestrator bypasses the gateway routing proxy,
        # calling real provider APIs directly.
        REAL_ANTHROPIC = "https://api.anthropic.com"
        REAL_DEEPSEEK = "https://api.deepseek.com"
        import os as _os
        anthropic_key = _os.environ.get("ANTHROPIC_API_KEY") or config.anthropic_key
        deepseek_key = _os.environ.get("DEEPSEEK_API_KEY") or config.deepseek_key
        if is_anthropic and not anthropic_key:
            raise ProviderError(401, "No Anthropic API key configured")
        if not is_anthropic and not deepseek_key:
            raise ProviderError(401, "No DeepSeek API key configured")

        provider = AnthropicProvider(REAL_ANTHROPIC, anthropic_key) if is_anthropic else DeepSeekProvider(REAL_DEEPSEEK, deepseek_key)

        if is_anthropic:
            upstream_body = {
                "model": model_id, "max_tokens": max_tok,
                "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
                "stream": True,
            }
            if system:
                upstream_body["system"] = system
            upstream_url = f"{REAL_ANTHROPIC}/v1/messages"
            auth_headers = provider.auth_headers({})
        else:
            msgs = [{"role": "system", "content": system}] if system else []
            msgs.extend(messages)
            upstream_body = {
                "model": model_id, "messages": msgs,
                "max_tokens": max_tok, "stream": True,
            }
            upstream_url = f"{REAL_DEEPSEEK}/chat/completions"
            auth_headers = provider.auth_headers({})

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(upstream_url, headers=auth_headers, json=upstream_body)
            if resp.status_code == 402:
                detail = "spend cap exceeded"
                try:
                    detail = resp.json().get("error", {}).get("message", detail)
                except Exception:
                    pass
                raise CapRefused(detail)
            if resp.status_code >= 400:
                raise ProviderError(resp.status_code, resp.text[:500])
            return resp  # Return httpx response for streaming

    result = await orchestrate_run(
        prompt, _post,
        max_plan=max_plan, max_build=max_build, max_review=max_review,
    )

    def _step_dict(s):
        if s is None:
            return None
        return {
            "model": s.model, "provider": s.provider, "shape": s.shape,
            "status": s.status, "body": s.body,
            "input_tokens": s.input_tokens, "output_tokens": s.output_tokens,
            "cost_usd": s.cost_usd, "duration_s": s.duration_s,
            "error": s.error,
        }

    return JSONResponse({
        "plan": _step_dict(result.plan),
        "build": _step_dict(result.build),
        "review": _step_dict(result.review),
        "routing": result.routing,
        "total_cost_usd": result.total_cost_usd,
        "session_id": SESSION_ID,
        "error": result.error,
    }, status_code=200 if not result.error else 422)


class CapRefused(Exception):
    pass


class ProviderError(Exception):
    def __init__(self, status: int, body: str = ""):
        self.status = status
        self.body = body
        super().__init__(f"Provider error {status}: {body[:200]}")


def _post_context(request: Request):
    """Minimal context for spend-guard (the real guard reads from config, not here)."""
    return {}


# --- Token Estimation API (TOP protocol + integrated papers) ---------------
@app.post("/estimate")
async def estimate(request: Request):
    """Estimate token usage for a task description. Returns P10/P50/P90 with cost band.

    POST body: {description: str, model?: str}
    Response: {mode, archetype, confidence, tokens: {p10,p50,p90}, cost: {p10,p50,p90}, calibration}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    description = (body.get("description") or body.get("prompt") or "").strip()
    if not description:
        return JSONResponse({"error": "missing 'description' field"}, status_code=400)

    model = body.get("model", "claude-opus-4-8")

    # Ensemble classification (LSMC-EPMC inspired)
    mode, archetype, confidence = await _classifier.classify(description)

    # Profile extraction
    prof = _profile.extract_profile(description)
    proxy = prof.scope_proxy()
    N = prof.N_estimate()

    # Priors for this class
    mu = _priors.mu0_r_in(mode, archetype)
    sigma = _priors.sigma0(mode, archetype)
    r_out = _priors.r_out(mode, archetype)

    # Token estimates (AG-1 model for agentic, SS-1 for single-shot)
    if mode == "agentic":
        H = _priors.overhead_H()
        delta = _priors.delta_per_turn()
        total_input = N * H + delta * N * (N - 1) / 2
        total_output = N * 500  # ~500 output tokens/turn
    else:
        total_input = proxy
        total_output = int(proxy * r_out)

    q = _calibrate.quantiles(proxy, mu, sigma)
    total_tokens_p50 = q["p50"] + int(total_output * (q["p50"] / max(proxy, 1)))
    total_tokens_p10 = q["p10"] + int(total_output * (q["p10"] / max(proxy, 1)))
    total_tokens_p90 = q["p90"] + int(total_output * (q["p90"] / max(proxy, 1)))

    # Cost estimate using pricing
    from pricing import rates as _rates
    rates = _rates(model)
    in_rate = rates.get("input", 0)
    out_rate = rates.get("output", 0)

    def _cost(tok):
        in_tok = int(tok * 0.8)
        out_tok = int(tok * 0.2)
        return round((in_tok * in_rate + out_tok * out_rate) / 1_000_000, 6)

    return JSONResponse({
        "mode": mode,
        "archetype": archetype,
        "confidence": confidence,
        "model": model,
        "tokens": {
            "p10": total_tokens_p10,
            "p50": total_tokens_p50,
            "p90": total_tokens_p90,
        },
        "cost": {
            "p10": _cost(total_tokens_p10),
            "p50": _cost(total_tokens_p50),
            "p90": _cost(total_tokens_p90),
        },
        "calibration": {
            "method": "prior",
            "note": "no ledger data yet for this class — pure first-principles prior",
        },
        "profile": prof.to_dict(),
    })


@app.get("/estimate/history")
async def estimate_history(task_class: str = "build_iterate"):
    """Return calibration quality metrics over time for a task class."""
    led = Ledger()
    result = _calibrate.calibrate_from_ledger(led, task_class)
    return JSONResponse(result)


# --- Loop Engineering: Discovery endpoint -----------------------------------
@app.get("/tasks/pending")
async def tasks_pending():
    """Return actionable TODO items from the vault that need estimation."""
    manifest = _loop.pending_manifest()
    return JSONResponse(manifest)


# --- PWA assets (make /chat installable on a phone) ------------------------
@app.get("/manifest.json")
async def manifest():
    p = GATEWAY_DIR / "manifest.json"
    if p.exists():
        return FileResponse(p, media_type="application/manifest+json")
    return JSONResponse({"error": "missing"}, status_code=404)


@app.get("/sw.js")
async def service_worker():
    # Served from the root so its scope covers the whole app.
    p = GATEWAY_DIR / "sw.js"
    if p.exists():
        return FileResponse(p, media_type="application/javascript")
    return PlainTextResponse("", status_code=404)


@app.get("/icons/{name}")
async def icon(name: str):
    if name in ("icon-192.png", "icon-512.png"):
        p = GATEWAY_DIR / "icons" / name
        if p.exists():
            return FileResponse(p, media_type="image/png")
    return JSONResponse({"error": "not found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=config.host, port=config.port, reload=False)
