#!/usr/bin/env python3
"""
overnight_loop.py — Production-grade overnight build loop. 85-95 quality.

Features (Task 1-4 hardened):
  1. WiFi-proof: 3 retries on network errors, checkpoint after every subtask, auto-resume
  2. Persistent memory: loads previous run's outputs as context, scores climb across runs
  3. Micro-task splitting: breaks large subtasks into file-sized micro-tasks so nothing truncates
  4. Atomic summaries: ATOMIC_SUMMARY.md + CROSS_RUN_SUMMARY.md for 30-second morning review

Usage:
    python tools/overnight_loop.py --task-file tools/cowork_task.txt --hours 8 --budget 14.50
    python tools/overnight_loop.py --task-file tools/cowork_task.txt --hours 8 --budget 14.50 --resume
    python tools/overnight_loop.py  # pulls tasks from vault
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# --- Config ---
GATEWAY_URL = "http://127.0.0.1:8787"
ANTHROPIC_BASE = "https://api.anthropic.com"

def _read_key(name):
    kf = Path(__file__).resolve().parents[1] / name
    if kf.exists():
        return kf.read_text(encoding="utf-8-sig").strip()
    return ""

ANTHROPIC_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
if not ANTHROPIC_KEY.startswith("sk-ant"):
    ANTHROPIC_KEY = _read_key(".anthropic-key")
DEEPSEEK_KEY = _read_key(".deepseek-key")

PRICING = {
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
    "deepseek-v4-pro": {"input": 0.435, "output": 0.87},
}

# --- WiFi-proof API helpers (3 retries, graceful exit on failure) ---

RETRY_NETWORK_ERRORS = (
    httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError,
    httpx.NetworkError, ConnectionError, OSError,
)

async def _call_anthropic_once(session, model, system, messages, max_tokens):
    body = {"model": model, "max_tokens": max_tokens, "stream": True,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages]}
    if system: body["system"] = system
    h = {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    t0 = time.monotonic(); text = ""; inp = out = 0
    async with session.stream("POST", f"{ANTHROPIC_BASE}/v1/messages", json=body, headers=h, timeout=300) as r:
        if r.status_code >= 400:
            bt = await r.aread()
            return {"body": "", "input_tokens": 0, "output_tokens": 0, "error": f"{r.status_code}: {bt[:200]}"}
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
                except Exception: continue
    cost = round((inp * PRICING[model]["input"] + out * PRICING[model]["output"]) / 1e6, 6)
    return {"body": text.strip(), "input_tokens": inp, "output_tokens": out, "cost": cost,
            "duration_s": round(time.monotonic() - t0, 1), "error": None}

async def _call_deepseek_once(session, model, system, messages, max_tokens):
    url = f"{GATEWAY_URL}/deepseek/v1/chat/completions"
    msgs = [{"role": "system", "content": system}] if system else []
    msgs.extend(messages)
    body = {"model": model, "messages": msgs, "max_tokens": max_tokens, "stream": True}
    t0 = time.monotonic(); text = ""; inp = out = 0
    async with session.stream("POST", url, json=body, timeout=300) as r:
        if r.status_code >= 400:
            bt = await r.aread()
            return {"body": "", "input_tokens": 0, "output_tokens": 0, "error": f"{r.status_code}: {bt[:200]}"}
        async for line in r.aiter_lines():
            if line.startswith("data:") and "data: [DONE]" not in line:
                try:
                    obj = json.loads(line[5:].strip())
                    c = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                    if c: text += c
                    if obj.get("usage"):
                        inp = obj["usage"].get("prompt_tokens", 0)
                        out = obj["usage"].get("completion_tokens", 0)
                except Exception: continue
    cost = round((inp * PRICING[model]["input"] + out * PRICING[model]["output"]) / 1e6, 6)
    return {"body": text.strip(), "input_tokens": inp, "output_tokens": out, "cost": cost,
            "duration_s": round(time.monotonic() - t0, 1), "error": None}

async def call_anthropic(session, model, system, messages, max_tokens, label=""):
    """WiFi-proof with 3 retries. On total failure, returns error dict (does not crash)."""
    for attempt in range(4):
        try:
            return await _call_anthropic_once(session, model, system, messages, max_tokens)
        except RETRY_NETWORK_ERRORS as e:
            if attempt < 3:
                wait = (attempt + 1) * 20
                print(f"  [retry {attempt+1}/3 {label} in {wait}s]", end="", flush=True)
                await asyncio.sleep(wait)
            else:
                return {"body": "", "input_tokens": 0, "output_tokens": 0, "cost": 0,
                        "duration_s": 0, "error": f"NETWORK FAIL after 3 retries ({label}): {e!r:.80}"}

async def call_deepseek(session, model, system, messages, max_tokens, label=""):
    """WiFi-proof with 3 retries."""
    for attempt in range(4):
        try:
            return await _call_deepseek_once(session, model, system, messages, max_tokens)
        except RETRY_NETWORK_ERRORS as e:
            if attempt < 3:
                wait = (attempt + 1) * 20
                print(f"  [retry {attempt+1}/3 {label} in {wait}s]", end="", flush=True)
                await asyncio.sleep(wait)
            else:
                return {"body": "", "input_tokens": 0, "output_tokens": 0, "cost": 0,
                        "duration_s": 0, "error": f"NETWORK FAIL after 3 retries ({label}): {e!r:.80}"}

# --- CHECKPOINT SYSTEM (Task 1) ---

def save_checkpoint(parent_dir, index, tasks, completed, total_spend, context, budget, deadline):
    """Save loop state. On crash/restart, resume from here."""
    ck = {
        "index": index, "total_tasks": len(tasks),
        "completed": completed, "total_spend": round(total_spend, 6),
        "budget_remaining": round(budget, 6),
        "deadline_remaining_s": max(0, deadline - time.monotonic()),
        "context_length": len(context),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tasks": [{"desc": t[0][:120], "source": t[1]} for t in tasks],
    }
    (parent_dir / "CHECKPOINT.json").write_text(json.dumps(ck, indent=2), encoding="utf-8")
    (parent_dir / "LOOP_CONTEXT.txt").write_text(context, encoding="utf-8")  # large, separate file

def load_checkpoint(parent_dir):
    """Return (index, tasks, completed, total_spend, context, budget, deadline) or None."""
    ckf = parent_dir / "CHECKPOINT.json"
    if not ckf.exists(): return None
    ck = json.loads(ckf.read_text(encoding="utf-8"))
    ctx = (parent_dir / "LOOP_CONTEXT.txt").read_text(encoding="utf-8") if (parent_dir / "LOOP_CONTEXT.txt").exists() else ""
    tasks = [(t["desc"], t["source"]) for t in ck["tasks"]]
    return (ck["index"], tasks, ck["completed"], ck["total_spend"], ctx,
            ck["budget_remaining"], time.monotonic() + ck.get("deadline_remaining_s", 28800))

# --- PREVIOUS RUN CONTEXT (Task 2) ---

def load_previous_run_context(repo_root):
    """Scan for previous loop output directories. Return best builds from each subtask."""
    prev_dirs = sorted(repo_root.glob("overnight_loop_*"), reverse=True)
    context_lines = []
    if not prev_dirs:
        return ""
    # Take the most recent completed run
    latest = prev_dirs[0]
    log = latest / "LOOP_LOG.md"
    if log.exists():
        context_lines.append(f"## Previous run: {latest.name}")
        context_lines.append(log.read_text(encoding="utf-8")[:2000])
    # Load best-scored build from each task
    for td in sorted(latest.glob("task_*")):
        final = td / "final_review.md"
        build = td / "build.md"
        if final.exists() and build.exists():
            review_text = final.read_text(encoding="utf-8")[:500]
            score_m = re.search(r"(\d{1,3})\s*/?\s*100", review_text)
            score = int(score_m.group(1)) if score_m else 0
            if score >= 50:  # only feed decent builds as context
                context_lines.append(f"\n### {td.name} (score: {score}/100)\n{build.read_text(encoding='utf-8')[:2000]}")
    return "\n".join(context_lines)

# --- MICRO-TASK SPLITTING (Task 3) ---

async def split_micro_tasks(session, task_desc, context):
    """If a subtask is too large, split it into 1-file micro-tasks."""
    if len(task_desc) < 60 and not any(kw in task_desc.lower() for kw in
        ["security", "engine", "full", "complete", "module", "registry", "harness"]):
        return [task_desc]  # already small enough

    r = await call_anthropic(session, "claude-opus-4-8",
        "Break this subtask into 2-4 micro-tasks. Each micro-task produces EXACTLY ONE file. Output one micro-task per line starting with '-'. Be specific about the filename. Example: '- Write sandbox.ts with path canonicalization and symlink defense'",
        [{"role": "user", "content": f"Break into single-file micro-tasks:\n\nSubtask: {task_desc}\n\nExisting context:\n{context[:1000]}"}], 2048)

    micro = []
    for line in r.get("body", "").splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)", line.strip())
        if m:
            micro.append(m.group(1).strip())
    return micro if micro else [task_desc]

# --- PROCESS ONE SUBTASK (5-step Generator/Evaluator, Opus for hard) ---

HARD_KW = ["security", "sandbox", "canonical", "symlink", "realpath", "engine",
           "agent loop", "plan -> act", "tool registry", "destructive", "confirmation"]

async def process_task(session, task_desc, out_dir, context="", use_opus=False):
    SYS_DESIGN = "Design concrete interfaces: function signatures, types, edge cases, error states, integration points."
    SYS_BUILD = "Produce ONE complete runnable file. Heading with exact path, fenced code block. No placeholders. All edge cases handled."
    SYS_REVIEW = "Score out of 100. List every issue: line numbers, missing edge cases, integration gaps. FIX-FIRST if any issue."
    SYS_FIX = "Fix EVERY issue from the review. Produce the corrected file in full."

    # ALL builds use Opus. DeepSeek quality ceiling is ~50. Opus starts at 70+.
    build_model = "claude-opus-4-8"
    BUILD_TOK = 128000  # Opus 4.8 max output — room for complete production code
    FIX_TOK = 64000
    steps = []; total = 0.0

    # 1. Design (Opus, 32K tokens — architecture must be perfect, mistakes propagate)
    r = await call_anthropic(session, "claude-opus-4-8", SYS_DESIGN,
        [{"role": "user", "content": f"Context (files this must integrate with):\n{context[:4000]}\n\nDesign this module. Be EXHAUSTIVELY SPECIFIC: exact function signatures with parameter types, return types, every edge case to handle, error states, and how it connects to existing files. This design is the build spec — nothing omitted."}], 32768, "design")
    steps.append(("design", r)); total += r.get("cost", 0)
    if r.get("error"): return {"steps": steps, "cost": total, "error": r["error"]}

    # 2. Build (Opus, 32K tokens — ONE complete file, no excuses)
    r = await call_anthropic(session, build_model, SYS_BUILD,
        [{"role": "user", "content": f"Context:\n{context[:3000]}\n\nDesign spec:\n{r['body'][:4000]}\n\nBuild EXACTLY what the design specifies. ONE complete file. Every edge case handled. No placeholders. No truncation accepted."}], BUILD_TOK, "build")
    steps.append(("build", r)); total += r.get("cost", 0)
    if r.get("error"): return {"steps": steps, "cost": total, "error": r["error"]}

    # 3. Review (Opus, 8K tokens — thorough)
    r = await call_anthropic(session, "claude-opus-4-8", SYS_REVIEW,
        [{"role": "user", "content": f"Review:\nDesign:\n{steps[0][1].get('body','')[:3000]}\n\nBuild:\n{steps[1][1].get('body','')[:8000]}"}], 8192, "review")
    steps.append(("review", r)); total += r.get("cost", 0)
    if r.get("error"): return {"steps": steps, "cost": total, "error": r["error"]}

    # 4. Fix (Opus, 16K tokens)
    r = await call_anthropic(session, "claude-opus-4-8", SYS_FIX,
        [{"role": "user", "content": f"Fix every issue:\n{steps[2][1].get('body','')[:3000]}\n\nOriginal:\n{steps[1][1].get('body','')[:2000]}"}], FIX_TOK, "fix")
    steps.append(("fix", r)); total += r.get("cost", 0)
    if r.get("error"): return {"steps": steps, "cost": total, "error": r["error"]}

    # 5. Quality loop: fix → review → repeat until score >= 85 (max 5 extra cycles)
    final = r.get("body", "") or steps[1][1].get("body", "")
    best_score = 0; quality_cycles = 0
    for q_cycle in range(6):  # up to 5 extra fix-review cycles
        r = await call_anthropic(session, "claude-opus-4-8", SYS_REVIEW,
            [{"role": "user", "content": f"Review. Score out of 100.\nTarget: 85-95. Be critical.\n\nOutput to review:\n{final[:8000]}"}], 8192, f"review-q{q_cycle}")
        steps.append((f"review_q{q_cycle}", r)); total += r.get("cost", 0)
        if r.get("error"): break

        # Extract score
        m = re.search(r"(\d{1,3})\s*/?\s*100", r.get("body", ""))
        score = int(m.group(1)) if m else 0
        best_score = max(best_score, score)
        quality_cycles = q_cycle

        if score >= 85:
            break
        if q_cycle < 5:
            print(f"  [score {score}/100, re-fixing...]", end="", flush=True)
            r = await call_anthropic(session, "claude-opus-4-8", SYS_FIX,
                [{"role": "user", "content": f"Fix EVERY issue:\n{r.get('body','')[:3000]}\n\nCurrent code:\n{final[:2000]}"}], FIX_TOK, f"fix-q{q_cycle}")
            steps.append((f"fix_q{q_cycle}", r)); total += r.get("cost", 0)
            if r.get("error"): break
            final = r.get("body", "") or final

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, step in steps:
        if step.get("body"):
            (out_dir / f"{name}.md").write_text(step["body"], encoding="utf-8")

    return {"steps": steps, "cost": total, "error": None, "build_body": final,
            "best_score": best_score, "quality_cycles": quality_cycles}

# --- ATOMIC SUMMARIES (Task 4) ---

def generate_summaries(parent_dir, all_runs_dir=None):
    """Generate ATOMIC_SUMMARY.md + CROSS_RUN_SUMMARY.md."""
    # Per-run summary
    lines = ["# ATOMIC SUMMARY", f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    scores = []; costs = []; issues_all = []

    for td in sorted(parent_dir.glob("task_*")):
        review_f = td / "final_review.md"
        if not review_f.exists(): continue
        text = review_f.read_text(encoding="utf-8")
        m = re.search(r"(\d{1,3})\s*/?\s*100", text)
        score = int(m.group(1)) if m else None
        # Find cost from LOOP_LOG
        cost_str = "?"
        log = parent_dir / "LOOP_LOG.md"
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines():
                if td.name in line and "Cost:" in line:
                    cost_str = line.split("Cost: $")[-1].split()[0] if "Cost: $" in line else "?"

        task_name = td.name
        # Extract first line of build as description
        build_f = td / "build.md"
        desc = task_name
        if build_f.exists():
            first = build_f.read_text(encoding="utf-8").split("\n")[0][:80]
            if first: desc = first

        if score is not None: scores.append(score)
        lines.append(f"### {task_name} — Score: {score}/100 | Cost: ${cost_str}")
        lines.append(f"{desc}")
        # Extract key issues
        for issue_line in text.splitlines():
            if any(kw in issue_line.lower() for kw in ["missing", "bug", "error", "fail", "incomplete", "vulnerab"]):
                issues_all.append(f"{task_name}: {issue_line.strip()[:120]}")
        lines.append("")

    # Trend
    if len(scores) >= 2:
        trend = "UP" if scores[-1] > scores[0] else "DOWN" if scores[-1] < scores[0] else "FLAT"
        lines.insert(3, f"**Score trend:** {trend} ({scores[0]} → {scores[-1]}) | **Tasks:** {len(scores)} | **Avg:** {sum(scores)/len(scores):.0f}/100")
    lines.insert(3, "")

    # Top issues
    lines.append("## Top Issues Found")
    for i in issues_all[:5]:
        lines.append(f"- {i}")

    # What to review first
    lines.append("")
    lines.append("## What to Review First")
    best = sorted([(s, td.name) for td in sorted(parent_dir.glob("task_*")) if (parent_dir / td.name / "final_review.md").exists()
                   for s in [int(re.search(r"(\d{1,3})\s*/?\s*100", (parent_dir / td.name / "final_review.md").read_text(encoding="utf-8")).group(1))
                             if re.search(r"(\d{1,3})\s*/?\s*100", (parent_dir / td.name / "final_review.md").read_text(encoding="utf-8")) else 0]], reverse=True)
    for s, name in best[:2]:
        lines.append(f"1. `{name}/` — scored {s}/100")
    # Flag low scores
    worst = [n for s, n in best if s < 50]
    if worst:
        lines.append(f"\n**Re-run needed (score < 50):** {', '.join(worst)}")

    (parent_dir / "ATOMIC_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    # Cross-run summary
    if all_runs_dir:
        runs = sorted(all_runs_dir.glob("overnight_loop_*"))
        if len(runs) >= 2:
            cr = ["# CROSS-RUN SUMMARY", "", "| Run | Tasks | Best Score | Total Cost |", "|-----|-------|-----------|------------|"]
            for rd in runs[-5:]:
                log = rd / "LOOP_LOG.md"
                alog = rd / "ATOMIC_SUMMARY.md"
                if alog.exists():
                    text = alog.read_text(encoding="utf-8")
                    scores_m = re.findall(r"Score:\s*(\d+)/100", text)
                    best_s = max(int(s) for s in scores_m) if scores_m else "?"
                    costs_m = re.findall(r"\$(\d+\.\d+)", text)
                    total_c = sum(float(c) for c in costs_m) if costs_m else 0
                    n_tasks = len([d for d in rd.glob("task_*") if d.is_dir()])
                    cr.append(f"| {rd.name} | {n_tasks} | {best_s} | ${total_c:.2f} |")
            cr.append("")
            (all_runs_dir / "CROSS_RUN_SUMMARY.md").write_text("\n".join(cr), encoding="utf-8")

# --- MAIN ---

async def main():
    ap = argparse.ArgumentParser(description="7C's Overnight Loop — 85-95 Quality")
    ap.add_argument("--task-file", help="master task file")
    ap.add_argument("--budget", type=float, default=14.50)
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--resume", action="store_true", help="resume from last checkpoint")
    args = ap.parse_args()

    budget = args.budget
    deadline = time.monotonic() + args.hours * 3600
    repo_root = Path(__file__).resolve().parents[1]
    parent_dir = Path(args.out or f"overnight_loop_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parent_dir.mkdir(parents=True, exist_ok=True)

    # --- CHECKPOINT RESUME ---
    tasks = []; accumulated = ""; total_spend = 0.0; start_idx = 0
    if args.resume or (parent_dir / "CHECKPOINT.json").exists():
        ck = load_checkpoint(parent_dir)
        if ck:
            start_idx, tasks, _, total_spend, accumulated, budget, deadline = ck
            print(f"RESUMED from checkpoint: task {start_idx+1}/{len(tasks)}, ${total_spend:.2f} spent, ${budget:.2f} remaining")

    if not tasks:
        # --- TASK LOADING ---
        prev_ctx = load_previous_run_context(repo_root)

        if args.task_file:
            master_task = Path(args.task_file).read_text(encoding="utf-8").strip()

            # Phase 0: Opus breaks master into subtasks (context-aware from previous runs)
            async with httpx.AsyncClient(timeout=600) as session:
                plan_prompt = f"Previous run context:\n{prev_ctx[:2000]}\n\nBreak this task into 6-12 sequential subtasks. Each subtask produces ONE file. Earlier subtasks produce files later ones depend on. Output one per line starting with '-'. Be specific about filenames.\n\nTask:\n{master_task}"
                r = await call_anthropic(session, "claude-opus-4-8",
                    "You are a technical project manager. Break the task into sequential single-file subtasks.",
                    [{"role": "user", "content": plan_prompt}], 4096)
                plan_cost = r.get("cost", 0); budget -= plan_cost
                print(f"Phase 0 plan: ${plan_cost:.4f} | Budget remaining: ${budget:.2f}")

                for line in r.get("body", "").splitlines():
                    m = re.match(r"^\s*[-*]\s+(.+)", line.strip())
                    if m: tasks.append((m.group(1).strip(), "subtask"))
                if not tasks: tasks = [(master_task, "fallback")]
                (parent_dir / "0_master_plan.md").write_text(r.get("body", ""), encoding="utf-8")

                # --- MICRO-TASK SPLITTING (Task 3) ---
                print(f"\nSubtasks before splitting: {len(tasks)}")
                micro_tasks = []
                for i, (t, s) in enumerate(tasks):
                    split = await split_micro_tasks(session, t, accumulated)
                    for st in split:
                        micro_tasks.append((st, s))
                tasks = micro_tasks
                print(f"After micro-task splitting: {len(tasks)}")

                # Feed previous context into accumulated
                if prev_ctx:
                    accumulated = prev_ctx[:4000]
        else:
            # Vault tasks
            try:
                async with httpx.AsyncClient(timeout=10) as cl:
                    r = await cl.get(f"{GATEWAY_URL}/tasks/pending")
                    if r.status_code == 200:
                        for t in r.json().get("tasks", []):
                            tasks.append((t["text"], t.get("file", "vault")))
            except Exception: pass
            if not tasks:
                tasks = [("Build the Cowork tab Phase 4", "plan")]

    # --- MAIN LOOP ---
    log_lines = [f"# 7C's Overnight Loop — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                 f"Budget: ${budget:.2f} | Tasks: {len(tasks)} | Start: {start_idx}", ""]
    completed = 0; failed = 0
    log_path = parent_dir / "LOOP_LOG.md"

    print(f"\n=== 7C's Overnight Loop ===")
    print(f"Budget: ${budget:.2f} | Tasks: {len(tasks)} | Start: {start_idx+1}")
    print()

    async with httpx.AsyncClient(timeout=600) as session:
        for i in range(start_idx, len(tasks)):
            if total_spend >= budget:
                print(f"BUDGET LIMIT: ${total_spend:.2f}"); break
            if time.monotonic() >= deadline:
                print(f"TIME LIMIT"); break

            task, source = tasks[i]
            is_hard = any(kw in task.lower() for kw in HARD_KW)
            builder = "Opus" if is_hard else "DS"

            task_dir = parent_dir / f"task_{i+1:03d}"
            label = task[:80].replace("→", "->").replace("—", "--").replace("–", "-")
            print(f"[{i+1}/{len(tasks)}] [{builder}] {label}... ", end="", flush=True)

            result = await process_task(session, task, task_dir, accumulated, use_opus=is_hard)
            cost = result["cost"]; total_spend += cost; err = result.get("error")

            if err:
                failed += 1
                print(f"ERR: {err[:80]} | ${cost:.4f} | total=${total_spend:.2f}")
                log_lines.append(f"### {i+1}: {label}\n**FAILED:** {err} | ${cost:.4f}")
                # Task 1: save checkpoint on failure
                save_checkpoint(parent_dir, i, tasks, completed + failed, total_spend, accumulated, budget, deadline)
                if "NETWORK" in err:
                    print("Network failure — checkpoint saved. Re-run with same --out to resume.")
                    break
            else:
                completed += 1
                # Extract score from quality loop
                best = result.get("best_score", 0)
                qc = result.get("quality_cycles", 0)
                score = str(best) if best > 0 else "?"
                if qc > 0:
                    score = f"{score} ({qc} re-fix)"
                # Accumulate context
                build_body = result.get("build_body", "")
                if build_body:
                    accumulated += f"\n## Task {i+1}: {task}\n{build_body[:3000]}\n"
                print(f"OK [{builder}] | ${cost:.4f} | {score}/100 | total=${total_spend:.2f}")
                log_lines.append(f"### Task {i+1}: {label}\n**OK [{builder}]** | {score}/100 | ${cost:.4f}")
                log_lines.append("")

                # Task 1: save checkpoint after every success
                save_checkpoint(parent_dir, i + 1, tasks, completed + failed, total_spend, accumulated, budget, deadline)

            log_path.write_text("\n".join(log_lines), encoding="utf-8")

    # --- STANDUP + SUMMARIES (Task 4) ---
    standup = [f"# MORNING STANDUP — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
               f"**Spent:** ${total_spend:.4f} / ${args.budget:.2f}",
               f"**Tasks:** {completed} done, {failed} failed",
               f"**Output:** {parent_dir}/", "",
               "## Next Steps",
               "1. Read `ATOMIC_SUMMARY.md` (30 seconds)",
               "2. Review best-scored builds",
               "3. Follow `daytime_checklist.md` for 100/100"]
    (parent_dir / "MORNING_STANDUP.md").write_text("\n".join(standup), encoding="utf-8")

    generate_summaries(parent_dir, repo_root)
    print(f"\n{'='*60}")
    print(f"DONE. {completed} tasks, ${total_spend:.4f}")
    print(f"Summary: {parent_dir}/ATOMIC_SUMMARY.md")
    print(f"Standup: {parent_dir}/MORNING_STANDUP.md")

if __name__ == "__main__":
    asyncio.run(main())
