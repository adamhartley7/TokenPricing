"""
Ensemble task classifier — LSMC-EPMC inspired.

Combines three weak classifiers for robust archetype assignment:
  1. Keyword matching (fast, zero-cost, but degenerate on vague descriptions)
  2. LLM zero-shot (accurate but costs ~$0.002/call — DeepSeek)
  3. Embedding k-NN (local, semantic similarity in Euclidean space)

The ensemble vote is weighted by classifier confidence.
Falls back through the hierarchy: archetype -> mode -> global prior.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import profile as _profile


# --- Classifier #1: Keyword (already in profile.py) ---
def _classify_keyword(description: str) -> tuple[str, float]:
    return _profile.classify_keyword(description)


# --- Classifier #2: LLM zero-shot ---
async def _classify_llm(description: str) -> tuple[str, float]:
    """Ask DeepSeek to classify the task into one of 6 archetypes."""
    import json
    import os
    import httpx

    key = os.environ.get("DEEPSEEK_API_KEY") or ""
    if not key:
        # Try reading from key file
        from pathlib import Path as _Path
        kf = _Path(__file__).resolve().parents[2] / ".deepseek-key"
        if kf.exists():
            key = kf.read_text(encoding="utf-8-sig").strip()
    if not key:
        return "build_iterate", 0.3

    prompt = (
        "Classify this task into exactly ONE archetype. Reply with ONLY the archetype name "
        "and a confidence 0-1.\n\n"
        "Archetypes: transform, extract, analyze, research, build_iterate, agent_loop\n\n"
        "Definitions:\n"
        "- transform: convert/rewrite/refactor/reformat existing material\n"
        "- extract: find/list/classify/parse/count from existing material\n"
        "- analyze: assess/compare/evaluate/summarise/judge\n"
        "- research: investigate/gather/survey/explore — needs external sources\n"
        "- build_iterate: build/implement/fix/create/develop code or content\n"
        "- agent_loop: orchestrate/automate a multi-step pipeline or workflow\n\n"
        f"Task: {description[:500]}\n\nArchetype:"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as cl:
            resp = await cl.post(
                "https://api.deepseek.com/chat/completions",
                headers={"authorization": f"Bearer {key}", "content-type": "application/json"},
                json={"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 32, "temperature": 0.0},
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"].strip().lower()
                for arch in ["transform", "extract", "analyze", "research", "build_iterate", "agent_loop"]:
                    if arch in text:
                        return arch, 0.75
                return "build_iterate", 0.4
    except Exception:
        pass
    return "build_iterate", 0.3


# --- Classifier #3: Embedding k-NN (placeholder — wired in embedding.py) ---
def _classify_embedding(description: str) -> tuple[str, float]:
    """Stub: will use fastembed + LanceDB k-NN when embedding.py is wired."""
    return "build_iterate", 0.0  # 0 confidence = abstain until wired


# --- Ensemble ---
async def classify(description: str, use_llm: bool = True) -> tuple[str, str, float]:
    """Ensemble classification. Returns (mode, archetype, confidence).

    Weighted vote across the three classifiers. Falls back through:
      archetype -> mode -> global prior (per PROTOCOL.md Section 10.1)
    """
    votes: dict[str, float] = {}

    # Classifier 1: Keyword (always runs, zero cost)
    arch1, conf1 = _classify_keyword(description)
    votes[arch1] = votes.get(arch1, 0) + conf1 * 0.4

    # Classifier 2: LLM zero-shot (cheap DeepSeek call)
    if use_llm:
        arch2, conf2 = await _classify_llm(description)
        votes[arch2] = votes.get(arch2, 0) + conf2 * 0.35

    # Classifier 3: Embedding k-NN
    arch3, conf3 = _classify_embedding(description)
    if conf3 > 0:
        votes[arch3] = votes.get(arch3, 0) + conf3 * 0.25

    if not votes:
        return "agentic", "build_iterate", 0.3

    best_arch = max(votes, key=votes.get)
    total = sum(votes.values())
    confidence = min(0.9, votes[best_arch] / max(total, 0.01))

    # Mode from archetype
    single_shot_arches = {"transform", "extract", "analyze"}
    mode = "single_shot" if best_arch in single_shot_arches else "agentic"

    return mode, best_arch, round(confidence, 3)
