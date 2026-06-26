#!/usr/bin/env python3
"""
orchestrate.py — CLI entry point for the 7C's Code tab pipeline.

Usage:
    python tools/orchestrate.py "Write a hello world script" --max-plan 8000 --max-build 16000 --max-review 8000

Uses the shared orchestrator engine (gateway/orchestrator.py) — same logic as the Code tab.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx

# Ensure we can import the gateway modules
GATEWAY_DIR = os.path.join(os.path.dirname(__file__), "..", "7ces", "gateway")
sys.path.insert(0, GATEWAY_DIR)

from orchestrator import CapRefused, ProviderError, orchestrate_run


async def _cli_post(gateway_url: str, path: str, body: dict):
    """Forward a request to the live gateway over HTTP."""
    full_url = f"{gateway_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=180.0) as cl:
        resp = await cl.post(full_url, json=body)
        if resp.status_code == 402:
            detail = "cap exceeded"
            try:
                detail = resp.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise CapRefused(detail)
        if resp.status_code >= 400:
            raise ProviderError(resp.status_code, resp.text[:500])
        return resp


async def main():
    ap = argparse.ArgumentParser(description="7C's Code tab orchestrator (CLI)")
    ap.add_argument("prompt", help="task description")
    ap.add_argument("--gateway", default="http://127.0.0.1:8787",
                    help="gateway URL (default http://127.0.0.1:8787)")
    ap.add_argument("--max-plan", type=int, default=8000)
    ap.add_argument("--max-build", type=int, default=16000)
    ap.add_argument("--max-review", type=int, default=8000)
    ap.add_argument("--output", "-o", help="write result JSON to this file")
    args = ap.parse_args()

    post = lambda path, body: _cli_post(args.gateway, path, body)

    print(f"Running: plan (Opus) → build (DeepSeek) → review (Opus)")
    result = await orchestrate_run(
        args.prompt, post,
        max_plan=args.max_plan, max_build=args.max_build, max_review=args.max_review,
    )

    def _step_dict(s):
        if s is None:
            return None
        return {
            "model": s.model, "provider": s.provider,
            "body": s.body[:500] + "..." if len(s.body) > 500 else s.body,
            "cost_usd": s.cost_usd, "duration_s": s.duration_s,
            "input_tokens": s.input_tokens, "output_tokens": s.output_tokens,
        }

    out = {
        "plan": _step_dict(result.plan),
        "build": _step_dict(result.build),
        "review": _step_dict(result.review),
        "routing": result.routing,
        "total_cost_usd": result.total_cost_usd,
        "error": result.error,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
        print(f"Wrote {args.output}")

    print(f"Total cost: ${result.total_cost_usd:.6f}")
    if result.error:
        print(f"Error: {result.error}")
    else:
        print("Pipeline complete.")


if __name__ == "__main__":
    asyncio.run(main())
