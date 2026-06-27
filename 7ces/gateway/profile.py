"""Profile extraction: turn a task description into a TaskProfile vector (D1-D12)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskProfile:
    """A structured profile of a task, extracted from its textual description."""
    mode: str = "agentic"         # "single_shot" | "agentic"
    archetype: str = "build_iterate"
    sub_tags: list[str] = field(default_factory=list)

    # D1-D12 feature dimensions from PROTOCOL.md Section 4
    d1_iteration_depth: str = "medium"          # low | medium | high
    d2_tool_round_trips: int = 5
    d3_input_volume_words: int = 0              # 0 = referenced, not inline
    d4_output_volume_words: int = 0
    d5_archetype: str = "build_iterate"
    d6_fan_out: int = 0
    d7_autonomy: str = "medium"                 # low | medium | high
    d8_determinism: str = "medium"
    d9_reasoning_intensity: str = "medium"
    d10_session_length: str = "medium"
    d11_cache_regime: str = "standard"
    d12_overhead_level: str = "central"

    # Derived
    n_retained_artifacts: int = 3
    external_acquisition_steps: int = 0
    verify_loops: int = 1
    retries: int = 1

    # Every field carries a source tag
    sources: dict[str, str] = field(default_factory=dict)  # field_name -> read|assumed|asked

    def N_estimate(self) -> int:
        """Estimate turn count from profile dimensions."""
        base = self.external_acquisition_steps + self.verify_loops + self.retries + 1
        if self.mode == "single_shot":
            return max(1, min(base, 5))
        return max(3, min(base, 80))

    def scope_proxy(self) -> int:
        """A size proxy: rough token estimate of the input material."""
        if self.d3_input_volume_words > 0:
            return int(self.d3_input_volume_words * 1.3)  # words → tokens
        return 500  # default for referenced-but-not-counted material

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "archetype": self.archetype,
            "sub_tags": self.sub_tags,
            "n_retained_artifacts": self.n_retained_artifacts,
            "external_acquisition_steps": self.external_acquisition_steps,
            "fan_out": self.d6_fan_out,
            "N_estimate": self.N_estimate(),
            "scope_proxy": self.scope_proxy(),
            "sources": self.sources,
        }


# --- Archetype classification (keyword-based, weak classifier #1) ---

_KEYWORDS = {
    "transform": [
        "convert", "rewrite", "translate", "reformat", "refactor",
        "migrate", "port", "rename", "restructure",
    ],
    "extract": [
        "find", "list", "classify", "parse", "count", "extract",
        "search for", "locate", "identify", "grep",
    ],
    "analyze": [
        "assess", "compare", "evaluate", "summarise", "summarize",
        "decide", "judge", "review", "audit", "grade", "score",
    ],
    "research": [
        "research", "investigate", "literature", "survey", "gather",
        "find out", "explore", "discover", "study", "learn about",
    ],
    "build_iterate": [
        "build", "implement", "fix", "debug", "add a", "create",
        "develop", "write", "code", "program", "design", "optimise",
        "optimize", "refactor", "extend", "modify", "update", "change",
    ],
    "agent_loop": [
        "orchestrat", "sub-agent", "pipeline", "batch", "end-to-end",
        "automate", "autonomous", "loop", "workflow", "multi-step",
    ],
}


def classify_keyword(description: str) -> tuple[str, float]:
    """Weak classifier #1: keyword matching. Returns (archetype, confidence)."""
    desc_lower = description.lower()
    scores = {}
    for arch, keywords in _KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in desc_lower)
        if hits > 0:
            scores[arch] = hits

    if not scores:
        return "build_iterate", 0.3  # fallback with low confidence

    best = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = min(0.7, scores[best] / total)  # cap at 0.7 for keyword-only
    return best, confidence


def extract_profile(description: str) -> TaskProfile:
    """Extract a TaskProfile from a task description.

    Currently uses keyword classification + heuristics. Will be upgraded to
    ensemble classifier (classifier.py) and embedding-based (embedding.py).
    """
    arch, confidence = classify_keyword(description)

    # Determine mode from archetype
    single_shot_arches = {"transform", "extract", "analyze"}
    mode = "single_shot" if arch in single_shot_arches else "agentic"

    profile = TaskProfile(
        mode=mode,
        archetype=arch,
        d5_archetype=arch,
        sources={"archetype": "assumed", "mode": "assumed"},
    )

    # Heuristic dimension estimates from description length and keywords
    desc_words = len(description.split())
    if desc_words < 20:
        profile.d1_iteration_depth = "low"
        profile.d7_autonomy = "low"
        profile.d10_session_length = "low"
    elif desc_words > 100:
        profile.d1_iteration_depth = "high"
        profile.d7_autonomy = "high"

    # Detect referenced material
    if any(w in description.lower() for w in ["file", "paper", "document", "codebase", "repo", "read"]):
        profile.d3_input_volume_words = 2000  # assume referenced material

    profile.sources.update({k: "assumed" for k in profile.sources if k != "archetype"})

    return profile
