```python
# Path: 7ces/gateway/cowork_config.py
"""
Cowork configuration: allowlist, budget, provider, API key.

Resolution order:
  1. Environment variables (COWORK_ALLOWLIST, COWORK_BUDGET, COWORK_PROVIDER, OPENAI_API_KEY)
  2. cowork_allowlist.json next to this file.
  3. Hard-coded defaults: empty allowlist, no budget, provider='openai'.

Public API:
  - load_allowlist()          -> list[str]       canonicalized, deduplicated directory paths
  - is_allowed(path, /)       -> bool            allowed for read/write after normalization
  - load_budget()             -> float           0.0 = unlimited, USD max cost
  - load_provider()           -> str             e.g. 'openai', 'azure', 'anthropic'
  - load_openai_api_key()     -> str | None
"""
import json
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ALLOWLIST_FILE = _HERE / "cowork_allowlist.json"


def _normalize(raw: str) -> str:
    """Resolve symlinks, home directories, make absolute."""
    p = os.path.abspath(os.path.expanduser(raw))
    try:
        p = os.path.realpath(p)
    except OSError:
        pass
    return p


def load_allowlist() -> list[str]:
    """Return a deduplicated list of canonicalized allowed directories."""
    raw_paths: set[str] = set()

    # 1. Environment variable
    env_raw = os.environ.get("COWORK_ALLOWLIST", "")
    if env_raw:
        for part in env_raw.split(os.pathsep):
            part = part.strip()
            if part:
                raw_paths.add(part)

    # 2. JSON file
    try:
        if _ALLOWLIST_FILE.exists():
            with _ALLOWLIST_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and "allow" in data:
                json_paths = data["allow"]
                if isinstance(json_paths, list):
                    for p in json_paths:
                        if isinstance(p, str) and p.strip():
                            raw_paths.add(p.strip())
    except (json.JSONDecodeError, OSError):
        pass

    return sorted({_normalize(p) for p in raw_paths})


def is_allowed(user_path: str) -> bool:
    """Check whether a given path is inside any allowed directory.

    The function normalizes the given path (absolute, resolved symlinks)
    and then verifies it starts with one of the allowed directories
    (plus a directory separator, to avoid prefix attacks like /etc/foo
    matching /etc).  If the allowlist is empty, *nothing* is allowed.

    Raises no exceptions; returns False if path doesn't exist or can't be
    resolved.
    """
    try:
        target = _normalize(user_path)
    except Exception:
        return False   # malformed path

    allowed = load_allowlist()
    if not allowed:
        return False
    for base in allowed:
        # ensure we don't match /etc when /etc/foo is inside, /etc + '/' == /etc/
        # but allow case-insensitive comparison on Windows.
        if os.name == "nt":
            target_lower = target.lower()
            base_lower = base.lower() + "\\"
            if target_lower == base_lower.rstrip("\\") or target_lower.startswith(base_lower):
                return True
        else:
            if target == base or target.startswith(base + "/"):
                return True
    return False


def load_budget() -> float:
    """Maximum allowed spending (USD).  0.0 means unlimited."""
    raw = os.environ.get("COWORK_BUDGET", "0.0").strip()
    try:
        val = float(raw)
        return max(0.0, val)
    except ValueError:
        return 0.0


def load_provider() -> str:
    """LLM provider name, e.g. 'openai', 'azure', 'anthropic'."""
    return os.environ.get("COWORK_PROVIDER", "openai").strip().lower()


def load_openai_api_key() -> str | None:
    """OpenAI API key from environment, or None."""
    return os.environ.get("OPENAI_API_KEY", None)
```

```json
// Path: 7ces/gateway/cowork_allowlist.json
{
  "allow": [
    "/home/user/projects/safe_dir",
    "C:/Users/User/Documents/workspace"
  ]
}
```

```python
# Path: 7ces/gateway/providers.py
"""
Provider abstraction wiring.

Currently supports 'openai'.  To add another provider (azure, anthropic,
local, etc.) implement the call_llm() function and register it in
PROVIDER_REGISTRY.

Public API:
  - call_llm(prompt: str, system: str | None = None) -> str
    Returns the LLM's text response, or raises RuntimeError on failure.
"""
import os
from typing import Dict, Any
from urllib.request import Request, urlopen
from urllib.error import URLError
import json
import sys

OPENAI_BASE = "https://api.openai.com/v1/chat/completions"
MODEL = os.environ.get("COWORK_MODEL", "gpt-4o")

PROVIDER_REGISTRY: Dict[str, Any] = {}


def _call_openai(prompt: str, system: str | None) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
    }).encode("utf-8")
    req = Request(
        OPENAI_BASE,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except URLError as e:
        raise RuntimeError(f"HTTP error: {e}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected response structure: {e}")


PROVIDER_REGISTRY["openai"] = _call_openai


def call_llm(prompt: str, system: str | None = None) -> str:
    # provider selection (from config) could be passed as arg or global
    # using the global config module to keep it simple
    from .cowork_config import load_provider  # relative import safe if run as module
    provider = load_provider()
    if provider not in PROVIDER_REGISTRY:
        raise RuntimeError(f"Unknown provider '{provider}'. Available: {list(PROVIDER_REGISTRY)}")
    return PROVIDER_REGISTRY[provider](prompt, system)
```

```python
# Path: 7ces/gateway/spend_guard.py
"""
Spend guard: track cumulative cost, enforce budget, estimate token usage.

Requires tiktoken for accurate token counting.
If tiktoken is not installed, falls back to rough estimate (chars/4).

Public API:
  - record_request(tokens_prompt: int, tokens_completion: int) -> None
  - current_cost() -> float
  - is_over_budget() -> bool
  - estimate_request_cost(prompt: str, expected_output_tokens: int) -> float
"""
import os
import threading
from typing import Optional

try:
    import tiktoken
    _TOKENIZER = tiktoken.encoding_for_model(os.environ.get("COWORK_MODEL", "gpt-4o"))
except ImportError:
    _TOKENIZER = None

# pricing per 1k tokens (input / output) for gpt-4o as default
Pricing = {
    "prompt": 0.005,
    "completion": 0.015,
}

_cumulative_cost = 0.0
_lock = threading.Lock()


def _count_tokens(text: str) -> int:
    if _TOKENIZER is not None:
        try:
            return len(_TOKENIZER.encode(text))
        except Exception:
            pass
    # fallback: rough approximation
    return len(text) // 4


def record_request(tokens_prompt: int, tokens_completion: int) -> None:
    """Add the cost of an LLM call to the running total."""
    global _cumulative_cost
    cost = (tokens_prompt / 1000.0 * Pricing["prompt"]) + \
           (tokens_completion / 1000.0 * Pricing["completion"])
    with _lock:
        _cumulative_cost += cost


def current_cost() -> float:
    with _lock:
        return _cumulative_cost


def estimate_request_cost(prompt: str, expected_output_tokens: int = 100) -> float:
    """Estimate cost of a call before making it (prevents budget overrun)."""
    prompt_tokens = _count_tokens(prompt)
    return (prompt_tokens / 1000.0 * Pricing["prompt"]) + \
           (expected_output_tokens / 1000.0 * Pricing["completion"])


def is_over_budget() -> bool:
    """Return True if spending has exceeded the configured budget."""
    from .cowork_config import load_budget  # relative import safe
    budget = load_budget()
    if budget <= 0.0:
        return False  # no limit
    return current_cost() >= budget
```

```python
# Path: 7ces/gateway/ui.py
"""
Terminal-based UI visualization using rich for dashboard-like output.

If rich is not installed, falls back to plain text print.

Public API:
  - display_conversation(messages: list[dict]) -> None
  - show_budget_status() -> None
  - confirm_action(description: str) -> bool
"""
import sys
from typing import List, Dict

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    console = None
    RICH_AVAILABLE = False


def display_conversation(messages: List[Dict[str, str]]) -> None:
    """Render the chat history."""
    if RICH_AVAILABLE:
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            style = "bold green" if role == "system" else ("bold cyan" if role == "assistant" else "default")
            console.print(Panel(content, title=role.capitalize(), style=style))
    else:
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            print(f"[{role}] {content}", file=sys.stderr)


def show_budget_status() -> None:
    """Print current cost, budget, and warning if exceeded."""
    from .spend_guard import current_cost, is_over_budget
    from .cowork_config import load_budget

    cost = current_cost()
    budget = load_budget()
    over = is_over_budget()
    msg = f"Spent: ${cost:.4f}"
    if budget > 0.0:
        msg += f" / Budget: ${budget:.2f}"
    if over:
        msg += " ⚠️  OVER BUDGET"

    if RICH_AVAILABLE:
        console.print(f"[bold red]{msg}" if over else f"[bold]{msg}")
    else:
        print(msg, file=sys.stderr)


def confirm_action(description: str) -> bool:
    """Prompt user for y/n confirmation (blocking)."""
    while True:
        resp = input(f"{description} (y/n): ").strip().lower()
        if resp in ("y", "yes"):
            return True
        if resp in ("n", "no"):
            return False
        print("Please answer y/n")
```

```python
# Path: 7ces/gateway/agent.py
"""
Main Cowork agent loop.

Uses the allowlist, provider, spend guard, and UI to interact with the
environment.  Reads commands from stdin, calls the LLM for decisions,
respects budget.

Run as:  python -m 7ces.gateway.agent
(Requires the package to be installed or run from the project root.)
"""
import sys
import json
import threading
import time
from typing import Optional
from .cowork_config import is_allowed, load_budget, load_provider
from .providers import call_llm
from .spend_guard import record_request, current_cost, estimate_request_cost, is_over_budget
from .ui import display_conversation, show_budget_status, confirm_action

_conversation: list[dict] = []

def _append(role: str, content: str):
    global _conversation
    _conversation.append({"role": role, "content": content})

def _process_command(user_input: str) -> Optional[str]:
    """Decide action based on user input. Returns None if exit."""
    cmd = user_input.strip().lower()
    if cmd in ("exit", "quit", "bye"):
        print("Goodbye.")
        return None

    # Example: allow reading/writing only if path is allowed
    if cmd.startswith("read ") or cmd.startswith("write "):
        _, path = cmd.split(" ", 1)
        path = path.strip().strip('"').strip("'")
        if not is_allowed(path):
            return f"❌ Access denied: '{path}' is not in the allowlist."
        # simulate readable file content
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()[:500]  # limit display
            return f"📄 {path}:\n{content}"
        except Exception as e:
            return f"❌ Error reading '{path}': {e}"
    # fallback: LLM
    return _call_llm_with_context(user_input)

def _call_llm_with_context(user_msg: str) -> str:
    """Build prompt from conversation, enforce budget, call LLM."""
    if is_over_budget():
        return "🚫 Budget exceeded. Cannot process further requests."
    context = "\n".join(f"{m['role']}: {m['content']}" for m in _conversation)
    prompt = f"{context}\nuser: {user_msg}\nassistant (be concise):"

    # Estimate cost and ask if budget is tight
    estimated = estimate_request_cost(prompt, expected_output_tokens=150)
    budget = load_budget()
    if 0.0 < budget and (current_cost() + estimated) > budget:
        if not confirm_action(f"This request will likely exceed the budget (${estimated:.4f}). Continue?"):
            return "Cancelled due to budget limits."

    try:
        response = call_llm(prompt, system="You are a helpful assistant with a CoWorker personality.")
        # simulate token counting (lack of actual token counts from provider)
        from .spend_guard import _count_tokens
        prompt_tokens = _count_tokens(prompt)
        response_tokens = _count_tokens(response)
        record_request(prompt_tokens, response_tokens)
        return response
    except Exception as e:
        return f"Provider error: {e}"

def main():
    print("Cowork agent started. Commands: read <path>, write <path>, or just chat. Type exit to quit.")
    show_budget_status()
    while True:
        try:
            user_input = input("\nYou: ").rstrip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if not user_input:
            continue
        result = _process_command(user_input)
        if result is None:
            break
        _append("user", user_input)
        _append("assistant", result)
        display_conversation([{"role": "assistant", "content": result}])
        show_budget_status()

if __name__ == "__main__":
    main()
```