#!/usr/bin/env python3
"""
comparison_test.py — 3-pipeline LLM comparison runner for 7C's.

Runs a task through three independent pipelines concurrently where possible:
  A: Opus (plan) -> DeepSeek (build) -> Opus (review)
  B: DeepSeek (plan) -> DeepSeek (build) -> DeepSeek (review)
  C: Ornith-1.0 (plan) -> Ornith-1.0 (build) -> Ornith-1.0 (review)

Then meta-reviews with Opus + DeepSeek, and a cost-effectiveness synthesis.

Usage:
    python tools/comparison_test.py "your task description"
    python tools/comparison_test.py --task-file prompt.txt
    python tools/comparison_test.py "task" --gateway http://127.0.0.1:8787 --ornith http://localhost:11434/v1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configuration & key loading (mirrors gateway/config.py)
# ---------------------------------------------------------------------------

GATEWAY_URL = "http://127.0.0.1:8787"
ORNITH_BASE = os.environ.get("ORNITH_API_BASE", "http://localhost:11434/v1")
ORNITH_MODEL = os.environ.get("ORNITH_MODEL", "ornith9b")

# Load Anthropic key from same sources as the gateway
def _read_key_file(name: str) -> str | None:
    repo_root = Path(__file__).resolve().parents[1]
    for p in (repo_root / name, repo_root / "7ces" / "gateway" / name, repo_root / "7ces" / name):
        if p.exists():
            try:
                val = p.read_text(encoding="utf-8-sig").strip()
                if val:
                    return val
            except OSError:
                continue
    return None

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY") or _read_key_file(".anthropic-key") or ""
ANTHROPIC_BASE = "https://api.anthropic.com"
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY") or _read_key_file(".deepseek-key") or ""
DEEPSEEK_BASE = "https://api.deepseek.com"

# Pricing per 1M tokens (USD) — mirrors pricing.json
PRICING = {
    "claude-opus-4-8":      {"input": 5.00, "output": 25.00, "cache_read": 0.50},
    "claude-sonnet-4-6":    {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "deepseek-v4-pro":      {"input": 0.435, "output": 0.87, "cache_read": 0.003625},
    "deepseek-v4-flash":    {"input": 0.14, "output": 0.28, "cache_read": 0.0028},
}

# Ornith self-host cost factors
ORNITH_COST_9B = 0.0003   # per 1K tokens
ORNITH_COST_35B = 0.0008  # per 1K tokens
ORNITH_COST_FACTOR = ORNITH_COST_9B  # we're using 9B


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute API cost for a model given token counts."""
    rates = PRICING.get(model)
    if not rates:
        return 0.0
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# API call helpers
# ---------------------------------------------------------------------------


async def call_gateway_stream(session: httpx.AsyncClient, provider: str, model: str,
                               system: str | None, messages: list[dict],
                               max_tokens: int = 4096) -> dict:
    """Call a provider through the 7C's gateway and return accumulated result."""
    is_anthropic = provider == "anthropic"
    if is_anthropic:
        url = f"{GATEWAY_URL}/{provider}/v1/messages"
        body = {
            "model": model, "max_tokens": max_tokens, "stream": True,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        }
        if system:
            body["system"] = system
    else:
        url = f"{GATEWAY_URL}/{provider}/v1/chat/completions"
        msgs = [{"role": "system", "content": system}] if system else []
        msgs.extend(messages)
        body = {"model": model, "messages": msgs, "max_tokens": max_tokens, "stream": True}

    t0 = time.monotonic()
    text_out = ""
    usage_in = usage_out = 0

    async with session.stream("POST", url, json=body, timeout=180.0) as resp:
        if resp.status_code == 402:
            detail = "cap exceeded"
            try:
                detail = (await resp.json()).get("error", {}).get("message", detail)
            except Exception:
                pass
            return {"body": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0.0, "duration_s": time.monotonic() - t0,
                    "error": f"402 cap refused: {detail}"}
        if resp.status_code >= 400:
            text = await resp.aread()
            return {"body": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0.0, "duration_s": time.monotonic() - t0,
                    "error": f"HTTP {resp.status_code}: {text[:300]}"}

        async for line in resp.aiter_lines():
            if line.startswith("data:") and not line.startswith("data: [DONE]"):
                try:
                    obj = json.loads(line[5:].strip())
                    if is_anthropic:
                        if obj.get("type") == "content_block_delta":
                            text_out += (obj.get("delta") or {}).get("text", "")
                        elif obj.get("type") == "message_start":
                            usage_in = (obj.get("message") or {}).get("usage", {}).get("input_tokens", 0)
                        elif obj.get("type") == "message_delta":
                            usage_out = (obj.get("usage") or {}).get("output_tokens", 0)
                    else:
                        text_out += (obj.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
                        if obj.get("usage"):
                            u = obj["usage"]
                            usage_in = u.get("prompt_tokens", 0)
                            usage_out = u.get("completion_tokens", 0)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    return {
        "body": text_out.strip(),
        "input_tokens": usage_in,
        "output_tokens": usage_out,
        "cost_usd": round(cost_usd(model, usage_in, usage_out), 6),
        "duration_s": round(time.monotonic() - t0, 2),
        "error": None,
    }


async def call_anthropic_direct(session: httpx.AsyncClient, model: str,
                                 system: str | None, messages: list[dict],
                                 max_tokens: int = 4096) -> dict:
    """Call Anthropic API directly (bypasses gateway which may route to DeepSeek)."""
    url = f"{ANTHROPIC_BASE}/v1/messages"
    body = {
        "model": model, "max_tokens": max_tokens, "stream": True,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
    }
    if system:
        body["system"] = system
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    t0 = time.monotonic()
    text_out = ""
    usage_in = usage_out = 0

    async with session.stream("POST", url, json=body, headers=headers, timeout=180.0) as resp:
        if resp.status_code >= 400:
            text = await resp.aread()
            return {"body": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0.0, "duration_s": time.monotonic() - t0,
                    "error": f"Anthropic HTTP {resp.status_code}: {text[:300]}"}

        async for line in resp.aiter_lines():
            if line.startswith("data:") and not line.startswith("data: [DONE]"):
                try:
                    obj = json.loads(line[5:].strip())
                    if obj.get("type") == "content_block_delta":
                        text_out += (obj.get("delta") or {}).get("text", "")
                    elif obj.get("type") == "message_start":
                        usage_in = (obj.get("message") or {}).get("usage", {}).get("input_tokens", 0)
                    elif obj.get("type") == "message_delta":
                        usage_out = (obj.get("usage") or {}).get("output_tokens", 0)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    return {"body": text_out.strip(), "input_tokens": usage_in, "output_tokens": usage_out,
            "cost_usd": round(cost_usd(model, usage_in, usage_out), 6),
            "duration_s": round(time.monotonic() - t0, 2), "error": None}


async def call_ornith(session: httpx.AsyncClient, messages: list[dict],
                      system: str | None = None, max_tokens: int = 4096) -> dict:
    """Call Ornith-1.0 via Ollama's OpenAI-compatible endpoint."""
    url = f"{ORNITH_BASE}/chat/completions"
    msgs = [{"role": "system", "content": system}] if system else []
    msgs.extend(messages)
    body = {"model": ORNITH_MODEL, "messages": msgs, "max_tokens": max_tokens,
            "temperature": 0.6, "top_p": 0.95}

    t0 = time.monotonic()
    async with session.stream("POST", url, json=body, timeout=600.0) as resp:
        if resp.status_code >= 400:
            text = await resp.aread()
            return {"body": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0.0, "duration_s": time.monotonic() - t0,
                    "error": f"Ornith HTTP {resp.status_code}: {text[:300]}"}

        text_out = ""
        usage_in = usage_out = 0
        async for line in resp.aiter_lines():
            if line.startswith("data:") and not line.startswith("data: [DONE]"):
                try:
                    obj = json.loads(line[5:].strip())
                    delta_content = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                    if delta_content:
                        text_out += delta_content
                    if obj.get("usage"):
                        usage_in = obj["usage"].get("prompt_tokens", 0)
                        usage_out = obj["usage"].get("completion_tokens", 0)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

        total_tokens = usage_in + usage_out or len(text_out.split()) * 2
        cost = round(total_tokens * ORNITH_COST_FACTOR / 1000, 6)

    return {"body": text_out.strip(), "input_tokens": usage_in, "output_tokens": usage_out,
            "cost_usd": cost, "duration_s": round(time.monotonic() - t0, 2), "error": None}


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


async def run_pipeline(name: str, plan_model: str, plan_provider: str,
                       build_model: str, build_provider: str,
                       review_model: str, review_provider: str,
                       task: str, session: httpx.AsyncClient,
                       is_ornith: bool = False) -> dict:
    """Run one plan->build->review pipeline."""
    result = {"name": name, "steps": {}, "total_cost": 0.0, "total_tokens": 0}

    async def call_step(provider, model, system, messages, max_tok=8192):
        if is_ornith:
            return await call_ornith(session, messages, system, max_tok)
        if provider == "anthropic":
            return await call_anthropic_direct(session, model, system, messages, max_tok)
        return await call_gateway_stream(session, provider, model, system, messages, max_tok)

    sys_plan = "You are a planning assistant. Produce a detailed implementation plan in 3-5 bullet points."
    sys_build = ("You produce concrete, ready-to-save files. For each file give a one-line heading "
                 "with its exact path, then a fenced code block with complete contents. No placeholders.")
    sys_review = ("You are a code reviewer. Be critical — check for bugs, missing files, incomplete code. "
                  "Verdict: APPROVE / APPROVE-WITH-NITS / FIX-FIRST / REJECT. List specific issues.")

    # Plan
    r = await call_step(plan_provider, plan_model, sys_plan,
                        [{"role": "user", "content": f"Plan this task:\n\n{task}"}],
                        max_tok=8192)
    result["steps"]["plan"] = {"model": plan_model, "provider": plan_provider, **r}

    if r["error"]:
        return result

    # Build
    build_input = f"Plan:\n\n{r['body']}\n\nTask:\n\n{task}"
    r = await call_step(build_provider, build_model, sys_build,
                        [{"role": "user", "content": f"Implement this plan:\n\n{build_input}"}],
                        max_tok=16384)
    result["steps"]["build"] = {"model": build_model, "provider": build_provider, **r}

    if r["error"]:
        return result

    # Review
    review_input = f"Task:\n{task}\n\nPlan:\n{result['steps']['plan']['body']}\n\nImplementation:\n{r['body']}"
    r = await call_step(review_provider, review_model, sys_review,
                        [{"role": "user", "content": (
                            f"Review this implementation. Give a score out of 100 with reasoning, "
                            f"strengths, weaknesses, and discrepancies.\n\n{review_input}")}],
                        max_tok=4096)
    result["steps"]["review"] = {"model": review_model, "provider": review_provider, **r}

    # Aggregate
    result["total_cost"] = sum(s.get("cost_usd", 0) for s in result["steps"].values())
    result["total_tokens"] = sum(
        s.get("input_tokens", 0) + s.get("output_tokens", 0) for s in result["steps"].values()
    )
    return result


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------


def write_file(out_dir: Path, filename: str, content: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / filename).write_text(content, encoding="utf-8")
    print(f"  [OK] {filename}")


def save_pipeline_files(out_dir: Path, pipe: dict, suffix: str):
    steps = pipe["steps"]
    for step_name in ("plan", "build", "review"):
        step = steps.get(step_name, {})
        if step.get("body"):
            write_file(out_dir, f"pipeline_{suffix}_{step_name}.md",
                       f"# {suffix.upper()} — {step_name}\n"
                       f"Model: {step.get('model')} | Provider: {step.get('provider')}\n"
                       f"Tokens: {step.get('input_tokens')}+{step.get('output_tokens')} | "
                       f"Cost: ${step.get('cost_usd', 0):.6f} | Duration: {step.get('duration_s')}s\n\n"
                       f"{step['body']}")


# ---------------------------------------------------------------------------
# Meta-review
# ---------------------------------------------------------------------------


async def meta_review(reviewer_name: str, model: str, provider: str,
                      task: str, pipelines: list[dict],
                      session: httpx.AsyncClient) -> dict:
    """One meta-reviewer compares all pipeline outputs."""
    review_prompt = f"Task:\n{task}\n\n"
    for p in pipelines:
        review_prompt += f"### {p['name']} (Cost: ${p['total_cost']:.6f})\n"
        for sn, step in p["steps"].items():
            body = step.get("body", "")[:2000]
            review_prompt += f"--- {sn} ({step.get('model')}) ---\n{body}\n\n"

    review_prompt += (
        "\nCompare these outputs. For each pipeline:\n"
        "- Rate out of 100 with detailed reasoning\n"
        "- Identify key strengths, weaknesses, discrepancies\n"
        "- Estimate cost (tokens × pricing) and compute value-per-dollar (score / cost)\n"
        "- If a pipeline failed, note it and score accordingly\n"
        "Present a clear comparison table."
    )

    sys = "You are a thorough, impartial evaluator. Be critical and precise."
    if provider == "anthropic":
        r = await call_anthropic_direct(session, model, sys,
                                        [{"role": "user", "content": review_prompt}],
                                        max_tokens=8192)
    else:
        r = await call_gateway_stream(session, provider, model, sys,
                                      [{"role": "user", "content": review_prompt}],
                                      max_tokens=8192)
    return {"reviewer": reviewer_name, "model": model, **r}


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def build_synthesis(task: str, pipelines: list[dict], meta_a: dict, meta_b: dict,
                    ornith_model_name: str) -> str:
    """Build the final comparison report."""
    lines = [
        "# Final Comparison Report",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Task:** {task[:200]}",
        "",
        "## Pipeline Summary",
        "",
        "| Pipeline | Models | Plan Tokens | Build Tokens | Review Tokens | Est. Cost |",
        "|----------|--------|-------------|--------------|---------------|-----------|",
    ]
    for p in pipelines:
        steps = p["steps"]
        pt = steps.get("plan", {}).get("input_tokens", 0) + steps.get("plan", {}).get("output_tokens", 0)
        bt = steps.get("build", {}).get("input_tokens", 0) + steps.get("build", {}).get("output_tokens", 0)
        rt = steps.get("review", {}).get("input_tokens", 0) + steps.get("review", {}).get("output_tokens", 0)
        models = "->".join(s.get("model", "?") for s in steps.values())
        lines.append(f"| {p['name']} | {models} | {pt} | {bt} | {rt} | ${p['total_cost']:.6f} |")

    lines += [
        "",
        "---",
        "",
        "## Meta-Review: Opus",
        meta_a.get("body", "_No output_"),
        "",
        "---",
        "",
        "## Meta-Review: DeepSeek",
        meta_b.get("body", "_No output_"),
        "",
        "---",
        "",
        "## Cost-Effectiveness Table",
        "",
        "| Pipeline | Est. Cost | Value/Cost | Notes |",
        "|----------|-----------|------------|-------|",
    ]
    for p in pipelines:
        cost = p["total_cost"]
        vc = "—" if cost == 0 else f"{100 / cost:.1f}"  # rough
        lines.append(f"| {p['name']} | ${cost:.6f} | {vc} | |")

    lines += [
        "",
        f"**Ornith model:** {ornith_model_name} (self-host cost: ${ORNITH_COST_FACTOR}/1K tokens)",
        "",
        "## Executive Recommendation",
        "",
        "_See meta-reviews above for detailed analysis._",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    global GATEWAY_URL, ORNITH_BASE, ORNITH_MODEL
    ap = argparse.ArgumentParser(description="7C's 3-pipeline LLM comparison test")
    ap.add_argument("task", nargs="?", help="task description (or use --task-file)")
    ap.add_argument("--task-file", help="read task from file")
    ap.add_argument("--gateway", default=GATEWAY_URL, help="7C's gateway URL")
    ap.add_argument("--ornith-base", default=ORNITH_BASE, help="Ornith OpenAI-compatible base URL")
    ap.add_argument("--ornith-model", default=ORNITH_MODEL, help="Ornith model name in Ollama")
    ap.add_argument("--out", help="output directory (default: comparison_test_<timestamp>)")
    ap.add_argument("--skip-ornith", action="store_true", help="skip Pipeline C if Ornith unavailable")
    args = ap.parse_args()

    GATEWAY_URL = args.gateway.rstrip("/")
    ORNITH_BASE = args.ornith_base.rstrip("/")
    ORNITH_MODEL = args.ornith_model

    task = args.task
    if args.task_file:
        task = Path(args.task_file).read_text(encoding="utf-8").strip()
    if not task:
        sys.exit("ERROR: provide a task description or --task-file")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out or f"comparison_test_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== 7C's 3-Pipeline Comparison Test ===")
    print(f"Task: {task[:100]}...")
    print(f"Output: {out_dir}")
    print(f"Gateway: {GATEWAY_URL}")
    print(f"Ornith: {ORNITH_BASE} ({ORNITH_MODEL})")
    print()

    async with httpx.AsyncClient(timeout=300.0) as client:

        # --- PIPELINE A: Opus->DeepSeek->Opus ---
        print("Pipeline A: Opus -> DeepSeek -> Opus")
        pipe_a = await run_pipeline("A (Opus->DeepSeek->Opus)",
                                    "claude-opus-4-8", "anthropic",
                                    "deepseek-v4-pro", "deepseek",
                                    "claude-opus-4-8", "anthropic",
                                    task, client)
        print(f"  Cost: ${pipe_a['total_cost']:.6f}, Tokens: {pipe_a['total_tokens']}")
        save_pipeline_files(out_dir, pipe_a, "A")
        write_file(out_dir, "pipeline_A_plan.md", pipe_a["steps"].get("plan", {}).get("body", ""))
        write_file(out_dir, "pipeline_A_output", pipe_a["steps"].get("build", {}).get("body", ""))
        write_file(out_dir, "pipeline_A_review.md", pipe_a["steps"].get("review", {}).get("body", ""))

        # --- PIPELINE B: Full DeepSeek ---
        print("Pipeline B: DeepSeek -> DeepSeek -> DeepSeek")
        pipe_b = await run_pipeline("B (Full DeepSeek)",
                                    "deepseek-v4-pro", "deepseek",
                                    "deepseek-v4-pro", "deepseek",
                                    "deepseek-v4-pro", "deepseek",
                                    task, client)
        print(f"  Cost: ${pipe_b['total_cost']:.6f}, Tokens: {pipe_b['total_tokens']}")
        save_pipeline_files(out_dir, pipe_b, "B")
        write_file(out_dir, "pipeline_B_plan.md", pipe_b["steps"].get("plan", {}).get("body", ""))
        write_file(out_dir, "pipeline_B_output", pipe_b["steps"].get("build", {}).get("body", ""))
        write_file(out_dir, "pipeline_B_review.md", pipe_b["steps"].get("review", {}).get("body", ""))

        # --- PIPELINE C: Full Ornith (optional) ---
        pipe_c = None
        if not args.skip_ornith:
            print("Pipeline C: Ornith -> Ornith -> Ornith")
            try:
                pipe_c = await run_pipeline("C (Full Ornith)",
                                            ORNITH_MODEL, "ornith",
                                            ORNITH_MODEL, "ornith",
                                            ORNITH_MODEL, "ornith",
                                            task, client, is_ornith=True)
                print(f"  Cost: ${pipe_c['total_cost']:.6f}, Tokens: {pipe_c['total_tokens']}")
                save_pipeline_files(out_dir, pipe_c, "C")
                write_file(out_dir, "pipeline_C_plan.md", pipe_c["steps"].get("plan", {}).get("body", ""))
                write_file(out_dir, "pipeline_C_output", pipe_c["steps"].get("build", {}).get("body", ""))
                write_file(out_dir, "pipeline_C_review.md", pipe_c["steps"].get("review", {}).get("body", ""))
            except Exception as e:
                import traceback
                print(f"  Ornith pipeline failed: {e}")
                traceback.print_exc()

        # --- META-REVIEWS ---
        all_pipes = [p for p in [pipe_a, pipe_b, pipe_c] if p is not None]
        print()

        print("Meta-Review: Opus")
        meta_opus = await meta_review("Opus", "claude-opus-4-8", "anthropic", task, all_pipes, client)
        print(f"  Cost: ${meta_opus.get('cost_usd', 0):.6f}")
        write_file(out_dir, "meta_review_opus.md", meta_opus.get("body", ""))

        print("Meta-Review: DeepSeek")
        meta_ds = await meta_review("DeepSeek", "deepseek-v4-pro", "deepseek", task, all_pipes, client)
        print(f"  Cost: ${meta_ds.get('cost_usd', 0):.6f}")
        write_file(out_dir, "meta_review_deepseek.md", meta_ds.get("body", ""))

        # --- SYNTHESIS ---
        print()
        print("Synthesis report...")
        report = build_synthesis(task, all_pipes, meta_opus, meta_ds, ORNITH_MODEL)
        write_file(out_dir, "final_comparison_report.md", report)

        # --- COST LOG ---
        cost_log = {
            "task": task[:200],
            "timestamp": datetime.now().isoformat(),
            "pipelines": {p["name"]: {"total_cost": p["total_cost"], "total_tokens": p["total_tokens"]}
                          for p in all_pipes},
            "meta_reviews": {
                "opus": {"cost": meta_opus.get("cost_usd", 0)},
                "deepseek": {"cost": meta_ds.get("cost_usd", 0)},
            },
            "grand_total": sum(p["total_cost"] for p in all_pipes) +
                           meta_opus.get("cost_usd", 0) + meta_ds.get("cost_usd", 0),
        }
        write_file(out_dir, "cost_log.json", json.dumps(cost_log, indent=2))

    # --- Summary ---
    print()
    print("=" * 60)
    print("COMPLETE")
    print(f"  Output: {out_dir}/")
    print(f"  Grand total: ${cost_log['grand_total']:.6f}")
    print(f"  Files: {len(list(out_dir.iterdir()))} generated")
    print(f"  Report: {out_dir / 'final_comparison_report.md'}")


if __name__ == "__main__":
    asyncio.run(main())
