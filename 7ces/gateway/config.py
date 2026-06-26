"""
7C's spend-guard gateway — configuration.

Loads caps, keys and endpoints from environment / a local .env file. SECRETS RULE: API keys
live only here (in memory, from .env or a git-ignored key file). They are never logged, never
returned to a client, and never put in a URL. Use `masked()` if you must show a key exists.

Keys resolve in this order (first hit wins):
  1. the matching environment variable (e.g. DEEPSEEK_API_KEY)
  2. a git-ignored key file at the *repo root* (.deepseek-key / .anthropic-key) — reuses the
     pattern already established by deepseek.ps1, so an existing cached key just works.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    # python-dotenv is optional at import time; if absent we just read os.environ.
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - trivial fallback
    def load_dotenv(*_a, **_k):  # type: ignore
        return False

GATEWAY_DIR = Path(__file__).resolve().parent          # .../7Cs/gateway
REPO_ROOT = GATEWAY_DIR.parents[1]                      # repo root (two levels up)

# Load 7Cs/gateway/.env if present (placeholders live in .env.example).
load_dotenv(GATEWAY_DIR / ".env")


def _read_key_file(name: str) -> str | None:
    """Read a git-ignored key file if present. Searches both the nested layout
    (<repo>/7Cs/gateway) and a standalone layout (<repo>/gateway), so the gateway works whether it
    lives inside the TokenPricing repo or in its own 7Cs repo."""
    for p in (REPO_ROOT / name, GATEWAY_DIR.parent / name, GATEWAY_DIR / name):
        if p.exists():
            try:
                # utf-8-sig strips a leading BOM — Windows PowerShell's `Set-Content -Encoding UTF8`
                # (as used by deepseek.ps1/glm.ps1) writes one, which would corrupt the auth header.
                val = p.read_text(encoding="utf-8-sig").strip()
                if val:
                    return val
            except OSError:
                continue
    return None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Config:
    """Singleton-ish settings object, read once at process start."""

    def __init__(self) -> None:
        # --- Keys (never logged) -------------------------------------------------
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or _read_key_file(".anthropic-key")
        self.deepseek_key = os.environ.get("DEEPSEEK_API_KEY") or _read_key_file(".deepseek-key")

        # --- Upstream base URLs (swap DeepSeek to a Western host for sensitive code) ---
        self.anthropic_base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        self.deepseek_base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.anthropic_version = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")

        # --- Spend caps (USD) — enforced BEFORE every paid call ------------------
        self.cap_per_request = _env_float("CAP_PER_REQUEST_USD", 0.50)
        self.cap_per_session = _env_float("CAP_PER_SESSION_USD", 2.00)
        self.cap_per_day = _env_float("CAP_PER_DAY_USD", 5.00)

        # Output is always bounded: if a request omits max_tokens we inject this, so the
        # worst-case output cost is never unbounded.
        self.default_max_tokens = _env_int("DEFAULT_MAX_TOKENS", 2048)

        # Safety factor applied to the pre-flight estimate so a slightly-low token estimate
        # still errs toward refusing rather than overspending (fail toward the cap).
        self.estimate_safety_factor = _env_float("ESTIMATE_SAFETY_FACTOR", 1.10)

        # --- Server ---------------------------------------------------------------
        self.host = os.environ.get("GATEWAY_HOST", "127.0.0.1")
        self.port = _env_int("GATEWAY_PORT", 8787)

        # --- Ledger ---------------------------------------------------------------
        self.ledger_path = os.environ.get("LEDGER_PATH", str(GATEWAY_DIR / "ledger.sqlite3"))

        # Request timeout to upstream providers (seconds).
        self.upstream_timeout = _env_float("UPSTREAM_TIMEOUT_S", 600.0)

    def key_for(self, provider: str) -> str | None:
        return {"anthropic": self.anthropic_key, "deepseek": self.deepseek_key}.get(provider)

    def caps(self) -> dict:
        return {
            "per_request_usd": self.cap_per_request,
            "per_session_usd": self.cap_per_session,
            "per_day_usd": self.cap_per_day,
        }


def masked(secret: str | None) -> str:
    """Safe representation of a secret for logs: presence + last 4 only."""
    if not secret:
        return "<missing>"
    return f"<set …{secret[-4:]}>" if len(secret) > 4 else "<set>"


# Module-level singleton used across the gateway.
config = Config()
