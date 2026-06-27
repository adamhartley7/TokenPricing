"""
Hybrid calibration — Bayesian update rule + Monte Carlo posterior sampling.

Implements PROTOCOL.md Section 10.3: blend first-principles priors with
logged actuals in log space, using shrinkage toward the prior.

The ensemble approach mirrors LSMC-EPMC: prior (behavioral swarm) +
shrinkage (geometric parser) + Monte Carlo (statistical stabilizer).
"""
from __future__ import annotations

import math
from typing import Any

import priors


def blend(
    prior_mu: float,
    prior_sigma: float,
    samples: list[float],  # log-ratios: ln(actual / proxy)
    k: int = 9,
    sigma_floor: float = 0.6,
) -> dict[str, Any]:
    """Bayesian shrinkage: blend prior with observed samples in log space.

    Returns {mu, sigma, method, n_eff, w} where w is data weight (0=cold, 1=fully data-driven).
    """
    n = len(samples)
    if n == 0:
        return {"mu": prior_mu, "sigma": max(prior_sigma, sigma_floor),
                "method": "prior", "n_eff": 0, "w": 0.0}

    # Effective sample size with recency weighting (simplified: unweighted)
    n_eff = n
    w = n_eff / (n_eff + k)  # data weight

    ybar = sum(samples) / n
    s = math.sqrt(sum((y - ybar) ** 2 for y in samples) / max(n - 1, 1)) if n > 1 else prior_sigma

    mu_star = (1 - w) * prior_mu + w * ybar
    sigma_star = math.sqrt((1 - w) * prior_sigma ** 2 + w * s ** 2)
    sigma_star = max(sigma_star, sigma_floor)

    method = "data" if n_eff >= 30 else "hybrid"
    return {"mu": mu_star, "sigma": sigma_star, "method": method,
            "n_eff": n_eff, "w": round(w, 3)}


def quantiles(proxy: float, mu: float, sigma: float, z: float = 1.2816) -> dict[str, float]:
    """Emit P10/P50/P90 token estimates from log-normal parameters."""
    p50 = proxy * math.exp(mu)
    p10 = proxy * math.exp(mu - z * sigma)
    p90 = proxy * math.exp(mu + z * sigma)
    return {"p10": round(p10), "p50": round(p50), "p90": round(p90)}


def scoreboard(rows: list[dict]) -> dict[str, Any]:
    """Compute calibration quality metrics from rows with both estimate_p50 and actual usage.

    Returns {bias, spread, coverage, n, p10_p90_coverage, one_sided_exceedance}.
    Bias > 1 means under-estimating. Coverage target is 0.80 (P10-P90 band).
    """
    if len(rows) < 3:
        return {"bias": 1.0, "spread": 1.0, "coverage": None, "n": len(rows),
                "ready": False, "note": "need >= 3 rows with estimates for calibration"}

    residuals = []
    covered = 0
    total = 0
    above_p90 = 0
    below_p10 = 0

    for r in rows:
        p50 = r.get("estimate_p50")
        actual = (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0)
        p10 = r.get("estimate_p10")
        p90 = r.get("estimate_p90")

        if p50 and actual and p50 > 0 and actual > 0:
            residuals.append(math.log(actual / p50))
            total += 1
            if p10 and p90:
                if p10 <= actual <= p90:
                    covered += 1
                if actual > p90:
                    above_p90 += 1
                if actual < p10:
                    below_p10 += 1

    if not residuals:
        return {"bias": 1.0, "spread": 1.0, "coverage": None, "n": len(rows), "ready": False}

    n_r = len(residuals)
    bias = math.exp(sum(residuals) / n_r)
    spread = math.exp(math.sqrt(sum((r - sum(residuals) / n_r) ** 2 for r in residuals) / max(n_r - 1, 1)))

    coverage = covered / max(total, 1) if total > 0 else None

    return {
        "bias": round(bias, 3),
        "spread": round(spread, 3),
        "coverage": round(coverage, 3) if coverage is not None else None,
        "n": len(rows),
        "ready": total >= 3,
        "above_p90_frac": round(above_p90 / max(total, 1), 3),
        "below_p10_frac": round(below_p10 / max(total, 1), 3),
    }


def calibrate_from_ledger(ledger, task_class: str, proxy: float = 500) -> dict[str, Any]:
    """Run calibration for a task class using ledger data."""
    rows = ledger.class_samples(task_class)
    arch = task_class.split("/")[-1] if "/" in task_class else "build_iterate"
    mode = "single_shot" if arch in ("transform", "extract", "analyze") else "agentic"

    prior_mu = priors.mu0_r_in(mode, arch)
    prior_sigma = priors.sigma0(mode, arch)
    k = priors.k_pseudocount(mode)
    floor = priors.sigma_floor(mode)

    # Build log-ratios from rows with estimates
    samples = []
    for r in rows:
        p50 = r.get("estimate_p50")
        actual = (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0)
        if p50 and actual and p50 > 0:
            samples.append(math.log(actual / p50))

    blended = blend(prior_mu, prior_sigma, samples, k, floor)
    q = quantiles(proxy, blended["mu"], blended["sigma"])
    sb = scoreboard(rows)

    return {"task_class": task_class, "proxy": proxy, **blended, "quantiles": q, "scoreboard": sb}
