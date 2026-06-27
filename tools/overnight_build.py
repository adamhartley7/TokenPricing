#!/usr/bin/env python3
"""
overnight_build.py — automated 95/100 pipeline for 7C's.

Runs a task through the full quality pipeline while you sleep:
  1. Opus plan           → what to build
  2. DeepSeek build · P1  → core engine + security layer
  3. DeepSeek build · P2  → UI + integration + tests
  4. Opus review          → critique with score
  5. Opus security audit  → focused vulnerability check
  6. DeepSeek test-gen    → E2E test scenarios
  7. Opus integration audit → cross-file verification with test results
  8. DeepSeek fix pass    → resolve issues found

Produces a timestamped output directory and MORNING_STANDUP.md.

Usage:
    python tools/overnight_build.py "Build a Cowork tab..."
    python tools/overnight_build.py --task-file prompt.txt
    python tools/overnight_build.py "task" --gateway http://127.0.0.1:8787
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
# Config & key loading
# ---------------------------------------------------------------------------

GATEWAY_URL = "http://127.0.0.1:8787"
ANTHROPIC_BASE = "https://api.anthropic.com"
DEEPSEEK_BASE = "https://api.deepseek.com"

def _read_key_file(name: str) -> str | None:
    repo_root = Path(__file__).resolve().parents[1]
    for p in (repo_root / name,):
        if p.exists():
            try:
                val = p.read_text(encoding="utf-8-sig").strip()
                if val: return val
            except OSError: continue
    return None

# Key file first (most reliable), env var as override only if it looks valid
_file_ak = _read_key_file(".anthropic-key") or ""
_env_ak = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
ANTHROPIC_KEY = _env_ak if _env_ak.startswith("sk-ant") else _file_ak

_file_dk = _read_key_file(".deepseek-key") or ""
_env_dk = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
DEEPSEEK_KEY = _env_dk if _env_dk.startswith("sk-") else _file_dk

PRICING = {
    "claude-opus-4-8": {"input": 5.00, "output": 25.00, "cache_read": 0.50},
    "deepseek-v4-pro": {"input": 0.435, "output": 0.87, "cache_read": 0.003625},
}

def cost_usd(model, inp, out):
    r = PRICING.get(model, {})
    return round((inp * r.get("input", 0) + out * r.get("output", 0)) / 1_000_000, 6)

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

async def call_anthropic(session, model, system, messages, max_tokens):
    url = f"{ANTHROPIC_BASE}/v1/messages"
    body = {"model": model, "max_tokens": max_tokens, "stream": True,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages]}
    if system: body["system"] = system
    headers = {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}

    t0 = time.monotonic(); text = ""; inp = out = 0
    async with session.stream("POST", url, json=body, headers=headers, timeout=300.0) as r:
        if r.status_code >= 400:
            body_text = await r.aread()
            return {"body": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0.0, "duration_s": time.monotonic() - t0,
                    "error": f"Anthropic {r.status_code}: {body_text[:300]}"}
        async for line in r.aiter_lines():
            if line.startswith("data:") and "data: [DONE]" not in line:
                try:
                    obj = json.loads(line[5:].strip())
                    if obj.get("type") == "content_block_delta":
                        text += (obj.get("delta") or {}).get("text", "")
                    elif obj.get("type") == "message_start":
                        inp = (obj.get("message") or {}).get("usage", {}).get("input_tokens", 0)
                    elif obj.get("type") == "message_delta":
                        out = (obj.get("usage") or {}).get("output_tokens", 0)
                except (json.JSONDecodeError, KeyError): continue
    return {"body": text.strip(), "input_tokens": inp, "output_tokens": out,
            "cost_usd": cost_usd(model, inp, out),
            "duration_s": round(time.monotonic() - t0, 2), "error": None}

async def call_deepseek(session, model, system, messages, max_tokens):
    """Call DeepSeek through the 7C's gateway (which has the correct key + endpoint)."""
    url = f"{GATEWAY_URL}/deepseek/v1/chat/completions"
    msgs = [{"role": "system", "content": system}] if system else []
    msgs.extend(messages)
    body = {"model": model, "messages": msgs, "max_tokens": max_tokens, "stream": True}

    t0 = time.monotonic(); text = ""; inp = out = 0
    async with session.stream("POST", url, json=body, timeout=300.0) as r:
        if r.status_code >= 400:
            body_text = await r.aread()
            return {"body": "", "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0.0, "duration_s": time.monotonic() - t0,
                    "error": f"DeepSeek {r.status_code}: {body_text[:300]}"}
        async for line in r.aiter_lines():
            if line.startswith("data:") and "data: [DONE]" not in line:
                try:
                    obj = json.loads(line[5:].strip())
                    c = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                    if c: text += c
                    if obj.get("usage"):
                        inp = obj["usage"].get("prompt_tokens", 0)
                        out = obj["usage"].get("completion_tokens", 0)
                except (json.JSONDecodeError, KeyError): continue
    return {"body": text.strip(), "input_tokens": inp, "output_tokens": out,
            "cost_usd": cost_usd(model, inp, out),
            "duration_s": round(time.monotonic() - t0, 2), "error": None}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class Log:
    def __init__(self, out_dir): self.out_dir = out_dir; self.total = 0.0; self.steps = []
    def p(self, msg): print(f"  {msg}")
    def step(self, name, result):
        c = result.get("cost_usd", 0); self.total += c
        dur = result.get("duration_s", 0)
        ok = " [OK]" if not result.get("error") else f" [ERR: {result['error'][:80]}]"
        self.p(f"{name}: ${c:.5f} · {dur:.1f}s{ok}")
        self.steps.append({"name": name, **result})
    def save(self, filename, content):
        if content: (self.out_dir / filename).write_text(content, encoding="utf-8")

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def run(task, out_dir):
    log = Log(out_dir)
    sys_plan = "You are an expert software architect. Produce a detailed implementation plan."
    sys_build = ("You produce concrete, complete, runnable files. For each file: a one-line heading "
                 "with exact path, then a fenced code block. No placeholders. No 'rest unchanged'.")
    sys_review = ("You are a critical code reviewer. Give a score out of 100 with detailed reasoning. "
                  "List specific strengths, weaknesses, discrepancies. Verdict: APPROVE / FIX-FIRST / REJECT.")
    sys_security = ("You are a security auditor. Focus ONLY on vulnerabilities: path traversal, "
                    "symlink escapes, injection, privilege escalation, race conditions, unsafe defaults. "
                    "List every finding with severity (CRITICAL/HIGH/MEDIUM/LOW) and a specific fix.")
    sys_integration = ("You are an integration tester. Read ALL provided files. Check: do function "
                       "signatures match across files? Do imports resolve? Does config flow to execution? "
                       "Do error handlers chain? List every cross-file inconsistency found.")
    sys_testgen = ("Generate a concrete end-to-end test script. Include: setup, execution, assertions, "
                   "cleanup. Cover the happy path AND failure modes (permission denied, path outside "
                   "allowlist, missing confirmation). Output a runnable script with expected output.")

    async with httpx.AsyncClient(timeout=600.0) as s:
        print("=== 7C's Overnight Build — 95/100 Pipeline ===\n")

        # 1. Opus Plan
        print("[1/8] Planning with Opus...")
        r = await call_anthropic(s, "claude-opus-4-8", sys_plan,
                                 [{"role": "user", "content": f"Plan this task in detail:\n\n{task}"}], 8192)
        log.step("1-plan", r); log.save("1_plan.md", f"# Plan\n\n{r['body']}")

        # 2. DeepSeek Build Pass 1 — Core + Security
        print("[2/8] DeepSeek building core engine + security...")
        ctx = f"Plan:\n{r['body']}\n\nBuild ONLY these workstreams: agent loop, scoped file access with allowlist, confirmation gating, sandbox isolation. Produce COMPLETE runnable files."
        r = await call_deepseek(s, "deepseek-v4-pro", sys_build,
                                [{"role": "user", "content": ctx}], 16384)
        log.step("2-build-core", r); log.save("2_build_core.md", r['body']); build1 = r['body']

        # 3. DeepSeek Build Pass 2 — UI + Integration + Tests
        print("[3/8] DeepSeek building UI + integration + tests...")
        ctx = f"Previous build produced:\n{build1[:2000]}\n\nNow build ONLY: UI visualization, provider abstraction wiring, spend-guard integration, configuration. Produce COMPLETE runnable files."
        r = await call_deepseek(s, "deepseek-v4-pro", sys_build,
                                [{"role": "user", "content": ctx}], 16384)
        log.step("3-build-ui", r); log.save("3_build_ui.md", r['body']); build2 = r['body']

        # 4. Opus Review
        print("[4/8] Opus reviewing all output...")
        ctx = f"Task:\n{task}\n\n## Build Pass 1 (Core + Security)\n{build1[:3000]}\n\n## Build Pass 2 (UI + Integration)\n{build2[:3000]}"
        r = await call_anthropic(s, "claude-opus-4-8", sys_review,
                                 [{"role": "user", "content": f"Review this implementation:\n\n{ctx}"}], 4096)
        log.step("4-review", r); log.save("4_review.md", r['body']); review = r['body']

        # 5. Opus Security Audit
        print("[5/8] Opus security audit...")
        ctx = f"Audit this code for security vulnerabilities:\n\n{build1[:4000]}"
        r = await call_anthropic(s, "claude-opus-4-8", sys_security,
                                 [{"role": "user", "content": ctx}], 4096)
        log.step("5-security", r); log.save("5_security_audit.md", r['body'])

        # 6. DeepSeek E2E Test Generation
        print("[6/8] DeepSeek generating E2E tests...")
        ctx = f"Code to test:\n{build1[:2000]}\n{build2[:2000]}\n\nGenerate an end-to-end test script."
        r = await call_deepseek(s, "deepseek-v4-pro", sys_testgen,
                                [{"role": "user", "content": ctx}], 16384)
        log.step("6-tests", r); log.save("6_e2e_tests.md", r['body']); tests = r['body']

        # 7. Opus Integration Audit
        print("[7/8] Opus integration audit (cross-file verification)...")
        ctx = f"All files:\n{build1[:2000]}\n{build2[:2000]}\n\nTests:\n{tests[:1000]}\n\nCheck cross-file consistency."
        r = await call_anthropic(s, "claude-opus-4-8", sys_integration,
                                 [{"role": "user", "content": ctx}], 8192)
        log.step("7-integration", r); log.save("7_integration_audit.md", r['body'])

        # 8. DeepSeek Self-Healing Fix Pass
        print("[8/8] DeepSeek fixing issues found...")
        ctx = f"Fix ALL issues identified in the review and security audit above. Original code:\n{build1[:1500]}\n{build2[:1500]}"
        r = await call_deepseek(s, "deepseek-v4-pro", sys_build,
                                [{"role": "user", "content": ctx}], 8192)
        log.step("8-fixes", r); log.save("8_fixes.md", r['body'])

    # --- MORNING_STANDUP.md ---
    standup = [
        "# MORNING STANDUP — Overnight 95/100 Build",
        f"**Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Task:** {task[:200]}",
        "",
        "## Pipeline Executed",
        "1. Opus plan (8,192 tok)",
        "2. DeepSeek build pass 1 — core engine + security (16,384 tok)",
        "3. DeepSeek build pass 2 — UI + integration (16,384 tok)",
        "4. Opus review with score",
        "5. Opus security audit — vulnerability scan",
        "6. DeepSeek E2E test generation",
        "7. Opus integration audit — cross-file verification",
        "8. DeepSeek self-healing fix pass",
        "",
        "## Cost",
        f"**Total: ${log.total:.5f}**",
        "",
        "## How to Complete the 100/100 (Daytime Steps)",
        "1. Read `4_review.md` — the Opus review with score",
        "2. Read `5_security_audit.md` — any vulnerabilities found?",
        "3. Read `7_integration_audit.md` — cross-file issues?",
        "4. Read `8_fixes.md` — what DeepSeek changed",
        "5. Run `daytime_checklist.md` for the manual verification steps",
        "6. Sign off: 'The output matches my intent' → 100/100",
        "",
        "## Files Produced",
    ]
    for s in log.steps:
        standup.append(f"- `{s['name']}`: ${s.get('cost_usd', 0):.5f} · {s.get('duration_s', 0):.1f}s"
                       f"{' · ERROR: ' + s['error'] if s.get('error') else ''}")

    standup.append("")
    standup.append("## Disposition")
    standup.append("Pipeline ran to completion. Review the outputs above, then follow `daytime_checklist.md` to reach 100/100.")
    standup.append(f"\n_Generated by overnight_build.py at 95/100 level_")

    log.save("MORNING_STANDUP.md", "\n".join(standup))
    log.save("cost_log.json", json.dumps({
        "task": task[:200], "timestamp": datetime.now().isoformat(),
        "steps": [{"name": s["name"], "cost": s.get("cost_usd", 0),
                    "input_tokens": s.get("input_tokens", 0),
                    "output_tokens": s.get("output_tokens", 0),
                    "error": s.get("error")} for s in log.steps],
        "total": log.total
    }, indent=2))

    print(f"\n{'='*60}")
    print(f"DONE. {len(log.steps)} steps · ${log.total:.5f}")
    print(f"Output: {out_dir}/")
    print(f"Standup: {out_dir}/MORNING_STANDUP.md")
    print()
    print("Tomorrow: follow daytime_checklist.md for 100/100.")
    return log


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def main():
    global GATEWAY_URL
    ap = argparse.ArgumentParser(description="7C's Overnight 95/100 Build Pipeline")
    ap.add_argument("task", nargs="?", help="task description")
    ap.add_argument("--task-file", help="read task from file")
    ap.add_argument("--gateway", default=GATEWAY_URL, help="7C's gateway URL (unused — direct API)")
    ap.add_argument("--out", help="output directory (default: overnight_build_<timestamp>)")
    args = ap.parse_args()

    GATEWAY_URL = args.gateway.rstrip("/")

    task = args.task
    if args.task_file:
        task = Path(args.task_file).read_text(encoding="utf-8").strip()
    if not task:
        sys.exit("ERROR: provide a task or --task-file")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out or f"overnight_build_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    await run(task, out_dir)


if __name__ == "__main__":
    asyncio.run(main())
