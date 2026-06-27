"""Load and expose priors.json for the token estimation pipeline."""
from __future__ import annotations

import json
from math import exp, log, sqrt
from pathlib import Path
from typing import Any

_GATEWAY_DIR = Path(__file__).resolve().parent
_PRIORS_PATH = _GATEWAY_DIR.parents[1] / "data" / "opus-work" / "priors.json"

# Fallback: if the TOP protocol priors aren't available, use bundled defaults
if not _PRIORS_PATH.exists():
    _PRIORS_PATH = _GATEWAY_DIR / "priors.json"

with open(_PRIORS_PATH, encoding="utf-8") as fh:
    _data = json.load(fh)

_version = _data.get("version", "0.1")
_log_space = _data.get("log_space", True)
_globals = _data.get("global_defaults", {})
_single_shot = _data.get("single_shot", {})
_agentic = _data.get("agentic", {})
_breadth_bands = _data.get("breadth_bands_turns", {})
_calibration = _data.get("_calibration_2026_06_25", {})


def global_default(key: str, default: Any = None) -> Any:
    """Read a global default from priors.json."""
    return _globals.get(key, default)


def for_archetype(mode: str, archetype: str) -> dict:
    """Return the prior dict for a given mode + archetype, or empty dict."""
    section = _single_shot if mode == "single_shot" else _agentic
    return section.get(archetype, {})


def N_prior_range(mode: str, archetype: str, breadth: str = "bounded") -> tuple[int, int]:
    """Return (low, high) turn-count prior for a mode/archetype/breadth combination."""
    arch = for_archetype(mode, archetype)
    N = arch.get("N_prior", {})
    band = N.get(breadth, N.get("bounded", [3, 8]))
    return (int(band[0]), int(band[1]))


def N_sigma(mode: str, archetype: str) -> float:
    """Return the log-space sigma for N prediction."""
    return float(for_archetype(mode, archetype).get("N_sigma", 0.8))


def mu0_r_in(mode: str, archetype: str) -> float:
    """Log-mean of total_input / scope_proxy ratio."""
    return float(for_archetype(mode, archetype).get("mu0_r_in", 0.0))


def r_out(mode: str, archetype: str) -> float:
    """Expected output/input token ratio."""
    return float(for_archetype(mode, archetype).get("r_out", 1.0))


def sigma0(mode: str, archetype: str) -> float:
    """Cold-start log-spread for a mode/archetype."""
    return float(for_archetype(mode, archetype).get("sigma0", 0.7))


def variance_class(mode: str, archetype: str) -> str:
    return str(for_archetype(mode, archetype).get("variance", "medium"))


def breadth_band(turns: int) -> str:
    """Map a turn count to a breadth band label (b1-b4)."""
    for label, (lo, hi) in _breadth_bands.items():
        if lo <= turns <= hi:
            return label
    return "b2"


def k_pseudocount(mode: str) -> int:
    return int(_globals.get("k_pseudocount", {}).get(mode, 5))


def sigma_floor(mode: str) -> float:
    return float(_globals.get("sigma_floor", {}).get(mode, 0.35))


def overhead_H(level: str = "central") -> int:
    return int(_globals.get("overhead_H_tokens", {}).get(level, 12000))


def delta_per_turn(level: str = "central") -> int:
    return int(_globals.get("delta_per_turn_tokens", {}).get(level, 1000))


def calibrated_H() -> int:
    return int(_calibration.get("H_eff", 12000))


def calibrated_delta() -> int:
    return int(_calibration.get("delta_eff", 1000))
