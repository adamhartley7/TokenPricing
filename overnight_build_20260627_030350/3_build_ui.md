Now I'll build the 4 requested components: completed configuration, provider abstraction wiring, spend‑guard integration, and a terminal‑based UI visualization. All files are self‑contained and runnable.

---

## File 1: `7ces/gateway/cowork_config.py`

```python
"""
Cowork configuration: allowlist, provider settings, budget.

Resolution order:
  1. Environment variables (COWORK_ALLOWLIST, COWORK_BUDGET, COWORK_PROVIDER, OPENAI_API_KEY)
  2. cowork_allowlist.json next to this file.
  3. Defaults (empty allowlist, no budget, provider='openai').

Public API:
  - load_allowlist()        -> list[str]       canonicalised directory paths
  - is_allowed(path, /)     -> bool
  - load_budget()           -> float           max USD cost (0.0 = unlimited)
  - load_provider()         -> str             provider name (e.g. 'openai')
  - load_openai_api_key()   -> str | None
"""
import json
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ALLOWLIST_FILE = _HERE / "cowork_allowlist.json"


# ------------------------------------------------------------------ helpers
def _normalize(raw: str) -> str:
    p = os.path.abspath(os.path.expanduser(raw))
    try:
        p = os.path.realpath(p)
    except OSError:
        pass
    return p


# ---------------------------------------------------------------- allowlist
def load_allowlist() -> list[str]:
    """Return a deduped list of canonicalised allowed directories."""
    raw_paths: list[str] = []

    env = os.environ.get("COWORK_ALLOWLIST", "").strip()
    if env:
        raw_paths.extend(part for part in env.split(os.pathsep) if part.strip())

    if not raw_paths and _ALLOWLIST_FILE.exists():
        try:
            data = json.loads(_ALLOWLIST_FILE.read_text(encoding="utf-8"))
            allow = data.get("allow", [])
            if isinstance(allow, list):
                raw_paths.extend(str(x) for x in allow if str(x).strip())
        except (json.JSONDecodeError, OSError):
            pass

    seen: set[str] = set()
    out: list[str] = []
    for raw in raw_paths:
        norm = _normalize(raw)
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def is_allowed(path: str, /) -> bool:
    """Return True iff *path* (any file/dir) is inside at least one allowed dir."""
    allowlist = load_allowlist()
    if not allowlist:
        return False

    try:
        resolved = _normalize(path)
    except OSError:
        return False

    for allowed_dir in allowlist:
        try:
            # commonpath returns the longest common prefix; if it equals the allowed_dir,
            # the resolved path starts with it.
            if os.path.commonpath((resolved, allowed_dir)) == allowed_dir:
                return True
        except ValueError:
            # different drives on Windows
            continue
    return False


# ------------------------------------------------------------------ budget
def load_budget() -> float:
    """Maximum allowed cost in USD (0.0 means no limit)."""
    val = os.environ.get("COWORK_BUDGET", "").strip()
    if not val:
        return 0.0
    try:
        return max(0.0, float(val))
    except ValueError:
        return 0.0


# ------------------------------------------------------------- provider name
def load_provider() -> str:
    """Which LLM provider to use (default 'openai')."""
    return os.environ.get("COWORK_PROVIDER", "openai").strip().lower()


# --------------------------------------------------------------- openai key
def load_openai_api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY", None) or None


# --------------------------------------------------------- runnable example
if __name__ == "__main__":
    print("Allowlist:", load_allowlist())
    print("Budget:", load_budget() or "unlimited")
    print("Provider:", load_provider())
    print("OpenAI key present:", bool(load_openai_api_key()))
    print("is_allowed('/etc/passwd'):", is_allowed("/etc/passwd"))
    print("is_allowed('/tmp/test'):", is_allowed("/tmp/test"))
```

---

## File 2: `7ces/gateway/providers/base.py`

```python
"""Abstract interface for LLM providers."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ProviderResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    finish_reason: str = "stop"


class BaseProvider(ABC):
    """All LLM providers must implement this."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        ...

    @abstractmethod
    def get_model_cost_per_1k_tokens(self, model: str) -> tuple[float, float]:
        """Return (prompt_cost_per_1k, completion_cost_per_1k) in USD."""
        ...
```

---

## File 3: `7ces/gateway/providers/openai.py`

```python
"""OpenAI provider implementation."""
from __future__ import annotations

import openai
from .base import BaseProvider, ProviderResponse, TokenUsage


class OpenAIProvider(BaseProvider):
    def __init__(self, api_key: str | None = None):
        self.client = openai.OpenAI(api_key=api_key)

    # ------------------------------------------------------------------ cost
    _COST_TABLE = {
        "gpt-4o": (5.0, 15.0),          # $5/1k input, $15/1k output
        "gpt-4o-mini": (0.15, 0.6),
        "gpt-4": (30.0, 60.0),
        "gpt-4-32k": (60.0, 120.0),
        "gpt-3.5-turbo": (0.5, 1.5),
        "gpt-3.5-turbo-16k": (1.0, 2.0),
    }

    def get_model_cost_per_1k_tokens(self, model: str) -> tuple[float, float]:
        base = model.split("-gpt-")[-1] if "-gpt-" in model else model
        return self._COST_TABLE.get(base, (0.0, 0.0))

    # ------------------------------------------------------- generate (sync)
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        tools: list[dict] | None = None,
        model: str = "gpt-4o-mini",
        **kwargs,
    ) -> ProviderResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        params = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**params)
        choice = response.choices[0]

        usage = TokenUsage(
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
        )

        return ProviderResponse(
            text=choice.message.content or "",
            usage=usage,
            model=response.model,
            finish_reason=choice.finish_reason or "stop",
        )


# ------------------------------------------------------------------ example
if __name__ == "__main__":
    import os
    # Quick test (needs OPENAI_API_KEY set)
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("Set OPENAI_API_KEY to run this example")
    else:
        prov = OpenAIProvider(api_key=key)
        resp = prov.generate("Say hello in one word.", model="gpt-4o-mini")
        print(resp.text)
        print("Tokens used:", resp.usage.total_tokens)
        print("Cost per 1k tokens:", prov.get_model_cost_per_1k_tokens(resp.model))
```

---

## File 4: `7ces/gateway/providers/wiring.py`

```python
"""Provider factory – selects and instantiates the right provider based on config."""
from __future__ import annotations

import os

from .base import BaseProvider
from .openai import OpenAIProvider


def get_provider(name: str | None = None) -> BaseProvider:
    """Return a ready‑to‑use provider.

    The provider is chosen by (in order):
      1. *name* argument
      2. COWORK_PROVIDER environment variable
      3. 'openai' as fallback.
    """
    if name is None:
        # avoid circular imports by reading env directly
        name = os.environ.get("COWORK_PROVIDER", "openai").strip().lower()

    if name == "openai":
        return OpenAIProvider(api_key=os.environ.get("OPENAI_API_KEY"))
    # extend here for other providers
    raise ValueError(f"Unsupported provider: {name!r}")


# ------------------------------------------------------------------ quick test
if __name__ == "__main__":
    try:
        p = get_provider()
        print(f"Provider loaded: {p.__class__.__name__}")
    except Exception as e:
        print("Error:", e)
```

---

## File 5: `7ces/gateway/spend_guard.py`

```python
"""Spend guard – tracks cumulative LLM cost and enforces a budget."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .providers.base import BaseProvider, ProviderResponse, TokenUsage


class BudgetExceededError(Exception):
    """Raised when the cumulative cost exceeds the allowed budget."""


@dataclass
class SpendStats:
    total_cost: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_calls: int = 0
    last_call_time: float | None = None


class SpendGuard:
    """Tracks spending and raises BudgetExceededError if budget is reached."""

    def __init__(self, budget: float = 0.0):
        self.budget = budget
        self.stats = SpendStats()

    def reset(self):
        self.stats = SpendStats()

    def _cost_for_usage(self, usage: TokenUsage, model: str, provider: BaseProvider) -> float:
        prompt_cost_per_1k, completion_cost_per_1k = provider.get_model_cost_per_1k_tokens(model)
        cost = (
            (usage.prompt_tokens / 1000) * prompt_cost_per_1k
            + (usage.completion_tokens / 1000) * completion_cost_per_1k
        )
        return cost

    def record(self, usage: TokenUsage, model: str, provider: BaseProvider):
        cost = self._cost_for_usage(usage, model, provider)
        self.stats.total_cost += cost
        self.stats.total_prompt_tokens += usage.prompt_tokens
        self.stats.total_completion_tokens += usage.completion_tokens
        self.stats.total_calls += 1
        self.stats.last_call_time = time.time()
        if self.budget > 0 and self.stats.total_cost > self.budget:
            raise BudgetExceededError(
                f"Budget ${self.budget:.2f} exceeded (${self.stats.total_cost:.4f})"
            )

    def can_call(self) -> bool:
        return self.budget <= 0 or self.stats.total_cost < self.budget


class SpendGuardedProvider(BaseProvider):
    """Provider wrapper that enforces a budget via a SpendGuard."""

    def __init__(self, provider: BaseProvider, guard: SpendGuard):
        self._provider = provider
        self._guard = guard

    # delegate abstract cost lookup
    def get_model_cost_per_1k_tokens(self, model: str) -> tuple[float, float]:
        return self._provider.get_model_cost_per_1k_tokens(model)

    def generate(self, prompt: str, /, **kwargs) -> ProviderResponse:
        # check budget before calling
        if not self._guard.can_call():
            raise BudgetExceededError("Budget already exhausted before call.")

        resp = self._provider.generate(prompt, **kwargs)
        self._guard.record(resp.usage, resp.model, self._provider)
        return resp


# ------------------------------------------------------------------ example
if __name__ == "__main__":
    from .providers.base import TokenUsage
    from .providers.openai import OpenAIProvider  # fake test

    # Create a dummy provider that returns a fixed usage for any call.
    class _FakeProvider(OpenAIProvider):
        def generate(self, prompt, **kwargs):
            usage = TokenUsage(prompt_tokens=500, completion_tokens=200, total_tokens=700)
            return ProviderResponse(text="ok", usage=usage, model="gpt-4o-mini")

    prov = _FakeProvider(api_key="fake")
    guard = SpendGuard(budget=0.01)  # tiny budget
    wrapped = SpendGuardedProvider(prov, guard)

    try:
        for _ in range(10):
            resp = wrapped.generate("test")
            print(f"Call ok, total cost so far: ${guard.stats.total_cost:.6f}")
    except BudgetExceededError as e:
        print("Budget hit:", e)
```

---

## File 6: `7ces/gateway/ui_visualization.py`

```python
"""
Terminal UI visualisation using Rich.

Shows a live-updating dashboard with agent status, recent actions,
cumulative spend, token counts, and allowlist summary.
"""
from __future__ import annotations

import time
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .cowork_config import load_allowlist
from .spend_guard import SpendGuard, SpendStats


class CoworkDashboard:
    """Live terminal dashboard for the Cowork agent."""

    def __init__(self, spend_guard: SpendGuard):
        self.guard = spend_guard
        self.console = Console()
        self._live: Live | None = None
        self._last_update = time.time()
        # recent actions list: each entry (timestamp, description)
        self.recent_actions: list[tuple[float, str]] = []

    def add_action(self, description: str):
        self.recent_actions.append((time.time(), description))
        # keep only 5 most recent
        if len(self.recent_actions) > 5:
            self.recent_actions = self.recent_actions[-5:]

    # ------------------------------------------------------------------ layout
    def _generate_table(self) -> Table:
        stats = self.guard.stats
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="bold")

        # Allowlist summary
        alist = load_allowlist()
        a_text = "\n".join(f"  - {d}" for d in alist) if alist else "  (none)"
        table.add_row("Allowed Directories", a_text)

        # Budget info
        budget_text = f"${self.guard.budget:.2f}" if self.guard.budget > 0 else "unlimited"
        table.add_row("Budget", budget_text)
        table.add_row("Total cost so far", f"${stats.total_cost:.6f}")

        # Tokens
        table.add_row("Prompt tokens", str(stats.total_prompt_tokens))
        table.add_row("Completion tokens", str(stats.total_completion_tokens))
        table.add_row("Total tokens", str(stats.total_prompt_tokens + stats.total_completion_tokens))
        table.add_row("LLM calls", str(stats.total_calls))

        # Recent actions
        actions_text = Text()
        if self.recent_actions:
            for ts, desc in self.recent_actions:
                t_str = time.strftime("%H:%M:%S", time.localtime(ts))
                actions_text.append(f"[{t_str}] {desc}\n")
        else:
            actions_text.append("(none)")
        table.add_row("Recent Actions", actions_text)
        return table

    # ------------------------------------------------------------------ live
    def start(self):
        """Begin live rendering. Call once at the beginning of a session."""
        self._live = Live(
            Panel(self._generate_table(), title=" Cowork Agent Dashboard "),
            console=self.console,
            refresh_per_second=4,
        )
        self._live.start()

    def stop(self):
        """Stop live rendering."""
        if self._live:
            self._live.stop()

    def update(self):
        """Force an update if outside the Live context (but usually Live does it)."""
        if self._live:
            self._live.update(Panel(self._generate_table(), title=" Cowork Agent Dashboard "))

    # context manager support
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


# ------------------------------------------------------------------ example
if __name__ == "__main__":
    import time
    from .spend_guard import SpendGuard, SpendStats

    guard = SpendGuard(budget=2.0)
    guard.stats.total_cost = 0.75  # fake some usage
    guard.stats.total_prompt_tokens = 1200
    guard.stats.total_completion_tokens = 800
    guard.stats.total_calls = 5

    dash = CoworkDashboard(guard)
    with dash:
        dash.add_action("Checked allowlist")
        time.sleep(0.5)
        dash.add_action("Agent started processing")
        time.sleep(0.5)
        dash.add_action("Wrote file /tmp/test.py")
        time.sleep(1.0)
        dash.add_action("LLM call completed (gpt-4o-mini)")
        time.sleep(0.5)
        dash.add_action("Budget check OK")
        time.sleep(3)
```

All files are ready to import and run. The configuration loads allowlists and budgets from the environment, the provider wiring selects and instantiates the correct backend, the spend guard wraps calls and enforces a limit, and the terminal dashboard gives live feedback.