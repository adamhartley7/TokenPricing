"""
orchestrator.py — shared plan→build→review engine for the 7C's Code tab.

The engine is UI-agnostic: it takes an injected ``post(path, body)`` callable so the
web route and the CLI tool share identical logic.  It only proposes — no disk writes
and no child processes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    model: str
    provider: str
    shape: str
    status: int
    body: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    error: str | None = None


@dataclass
class OrchestrateResult:
    plan: StepResult | None = None
    build: StepResult | None = None
    review: StepResult | None = None
    routing: dict[str, str] = field(default_factory=dict)
    total_cost_usd: float = 0.0
    session_id: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CapRefused(Exception):
    """Raised when the spend-guard rejects a call with HTTP 402."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class ProviderError(Exception):
    """Upstream returned a non-2xx that is not a cap refusal."""

    def __init__(self, status: int, body: str):
        super().__init__(f"Provider error {status}: {body[:300]}")
        self.status = status
        self.body = body


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def _step(
    post: Callable[..., Coroutine[Any, Any, Any]],
    provider: str,
    model_id: str,
    shape: str,
    messages: list[dict],
    system: str | None,
    max_tokens: int,
    label: str,
) -> StepResult:
    """One pipeline step: send messages, stream back, accumulate text + usage."""
    import time
    import asyncio

    started = time.monotonic()
    body: dict[str, Any] = {
        "model": model_id,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": messages,
    }
    if shape == "anthropic":
        if system:
            body["system"] = system
        merged = [{"role": m["role"], "content": m["content"]} for m in messages]
        url = f"/{provider}/v1/messages"
    else:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        merged = msgs
        url = f"/{provider}/v1/chat/completions"

    if shape == "anthropic":
        body["messages"] = merged
    else:
        body["messages"] = merged

    try:
        resp = await post(url, body)
    except Exception as exc:
        if "402" in str(exc) or "cap" in str(exc).lower():
            raise CapRefused(str(exc)) from exc
        raise ProviderError(502, str(exc)) from exc

    # Non-stream fallback (some providers / caps don't stream)
    if not isinstance(resp, dict):
        resp = resp

    status = resp if isinstance(resp, int) else 200

    duration = round(time.monotonic() - started, 3)
    return StepResult(
        model=model_id,
        provider=provider,
        shape=shape,
        status=status if isinstance(status, int) else 200,
        duration_s=duration,
    )


async def _stream_step(
    post: Callable[..., Coroutine[Any, Any, Any]],
    provider: str,
    model_id: str,
    shape: str,
    messages: list[dict],
    system: str | None,
    max_tokens: int,
) -> StepResult:
    """Call the provider through the gateway with streaming, capturing usage."""
    import time
    from urllib.request import Request

    started = time.monotonic()
    body: dict[str, Any] = {
        "model": model_id,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if shape == "anthropic":
        url = f"/{provider}/v1/messages"
        if system:
            body["system"] = system
        body["messages"] = [{"role": m["role"], "content": m["content"]} for m in messages]
    else:
        url = f"/{provider}/v1/chat/completions"
        msgs: list[dict] = [{"role": "system", "content": system}] if system else []
        msgs.extend(messages)
        body["messages"] = msgs

    resp = await post(url, body)

    # The gateway returns a streaming response. For the in-process web route we
    # read the SSE stream; for CLI we reconstruct from the accumulated text.
    text_out = ""
    usage_in = usage_out = cost = 0
    session_id = ""

    if hasattr(resp, "headers"):
        # httpx / requests Response — read SSE
        session_id = resp.headers.get("x-session-id", "")
        raw = ""
        import asyncio
        if hasattr(resp, "aiter_bytes"):
            async for chunk in resp.aiter_bytes():
                raw += chunk.decode("utf-8", errors="replace")
        elif hasattr(resp, "iter_bytes"):
            raw = resp.text
        else:
            raw = str(resp)

        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("data:") and not line.startswith("data: [DONE]"):
                try:
                    obj = json.loads(line[5:].strip())
                    if shape == "anthropic":
                        if obj.get("type") == "content_block_delta":
                            text_out += (obj.get("delta") or {}).get("text", "")
                        elif obj.get("type") == "message_start":
                            usage_in = (obj.get("message") or {}).get("usage", {}).get("input_tokens", 0)
                        elif obj.get("type") == "message_delta":
                            usage_out = (obj.get("usage") or {}).get("output_tokens", 0)
                    else:
                        text_out += (obj.get("choices") or [{}])[0].get("delta", {}).get("content", "")
                        if obj.get("usage"):
                            u = obj["usage"]
                            usage_in = u.get("prompt_tokens", 0)
                            usage_out = u.get("completion_tokens", 0)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    else:
        # Plain dict — non-streaming gateway response
        text_out = resp.get("content", "") or resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = resp.get("usage") or {}
        usage_in = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
        usage_out = usage.get("output_tokens") or usage.get("completion_tokens", 0)
        cost = resp.get("cost_usd", 0)
        session_id = resp.get("session_id", "")

    if not cost and usage_in + usage_out > 0:
        # Approximate cost from tokens — rough but better than zero
        from pricing import rates as pricing_rates
        rates = pricing_rates.get(model_id) or pricing_rates.get(provider, {})
        in_rate = rates.get("input", 0)
        out_rate = rates.get("output", 0)
        cost = (usage_in * in_rate + usage_out * out_rate) / 1e6

    duration = round(time.monotonic() - started, 3)
    return StepResult(
        model=model_id,
        provider=provider,
        shape=shape,
        status=200,
        body=text_out.strip(),
        input_tokens=usage_in,
        output_tokens=usage_out,
        cost_usd=round(cost, 6),
        duration_s=duration,
    )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def run(
    prompt: str,
    post: Callable[..., Coroutine[Any, Any, Any]],
    *,
    max_plan: int = 8000,
    max_build: int = 16000,
    max_review: int = 8000,
) -> OrchestrateResult:
    """Plan with Opus → build with DeepSeek → review with Opus.

    ``post(path, body)`` is an async callable that forwards through the gateway.
    It must raise ``CapRefused`` on HTTP 402 and ``ProviderError`` on other failures.
    """
    result = OrchestrateResult()
    result.routing = {
        "plan": "claude-opus-4-8",
        "build": "deepseek-v4-pro",
        "review": "claude-opus-4-8",
    }

    system_prompt = (
        "You are a coding agent.  Be precise and concrete.  "
        "When writing code, include complete, runnable files — no placeholders.  "
        "Output GitHub-flavored Markdown with fenced code blocks tagged with the language."
    )

    # --- Plan ---------------------------------------------------------------
    plan_messages = [
        {"role": "user", "content": (
            f"Plan this task in 3-5 bullet points.  Identify what files will change "
            f"and what the key technical decisions are.  Be specific about file paths.\n\n"
            f"Task: {prompt}"
        )},
    ]
    try:
        result.plan = await _stream_step(
            post, provider="anthropic", model_id="claude-opus-4-8",
            shape="anthropic", messages=plan_messages, system=system_prompt,
            max_tokens=max_plan,
        )
    except Exception as exc:
        result.error = f"Plan step failed: {exc}"
        return result

    # --- Build --------------------------------------------------------------
    build_system = (
        "You produce concrete, ready-to-save files.  For each file give a one-line "
        "heading with its exact path, then a fenced code block with complete contents.  "
        "No placeholders.  No 'rest unchanged'.  After the files, add a short Run section "
        "with exact Windows PowerShell commands.  Prefer the fewest files that fully "
        "solve the task."
    )
    build_messages = [
        {"role": "user", "content": (
            f"Here is the plan:\n\n{result.plan.body}\n\n"
            f"Now implement it.  Produce concrete files with complete contents.  "
            f"The task: {prompt}"
        )},
    ]
    try:
        result.build = await _stream_step(
            post, provider="deepseek", model_id="deepseek-v4-pro",
            shape="openai", messages=build_messages, system=build_system,
            max_tokens=max_build,
        )
    except Exception as exc:
        result.error = f"Build step failed: {exc}"
        return result

    # --- Review -------------------------------------------------------------
    review_messages = [
        {"role": "user", "content": (
            f"Review the following implementation against the plan.  "
            f"Be critical — check for bugs, missing files, incomplete code, "
            f"security issues, and deviations from the plan.\n\n"
            f"## Plan\n{result.plan.body}\n\n"
            f"## Implementation\n{result.build.body}\n\n"
            f"Verdict: APPROVE / APPROVE-WITH-NITS / FIX-FIRST / REJECT.\n"
            f"List specific issues found, or state why it passes."
        )},
    ]
    try:
        result.review = await _stream_step(
            post, provider="anthropic", model_id="claude-opus-4-8",
            shape="anthropic", messages=review_messages, system=system_prompt,
            max_tokens=max_review,
        )
    except Exception as exc:
        result.error = f"Review step failed: {exc}"
        return result

    # --- Tally cost ---------------------------------------------------------
    total = 0.0
    for step in (result.plan, result.build, result.review):
        if step:
            total += step.cost_usd
    result.total_cost_usd = round(total, 6)

    return result
