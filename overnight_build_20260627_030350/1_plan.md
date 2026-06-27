# Plan

# Cowork Tab — Phase 4 Implementation Plan

This plan delivers a complete, runnable multi-step agent harness for the 7C's app. I'll structure it as: (1) architecture decisions, (2) new files with full contents, (3) integration edits, (4) tests, (5) Run section.

---

## Architecture Decisions

**Module layout** (new files under `7ces/gateway/`):

| File | Purpose |
|------|---------|
| `coworkfs.py` | Scoped filesystem with `fs.realpath` canonicalization + `path.relative` belt-and-suspenders. Deny-by-default. |
| `cowork_tools.py` | Tool registry: `list_dir`, `read_file` (read-only), `write_file`, `delete_file`, `move_file`, `run_shell` (destructive). Each tool declares `destructive`, `risk`, and an `affected_paths` preview. |
| `cowork.py` | Agent engine: plan→act→observe→reflect loop. Provider-pluggable. Streams events. Pauses on destructive ops awaiting confirmation. |
| `cowork_config.py` | Loads allowlist from `cowork_allowlist.json` (env-overridable). |
| Edits to `app.py` | New routes: `POST /cowork/start`, `POST /cowork/step`, `POST /cowork/confirm`, `GET /cowork/events/{session_id}` (SSE). Serve Cowork UI. |
| Edits to `chat.html` | Add Cowork tab + JS client. |

**Key design choices:**

1. **Session-based state machine.** Because destructive ops need confirmation mid-loop, the agent can't run to completion in one request. We use a server-side session object that holds loop state and *suspends* when it hits a destructive tool, emitting a `confirmation_required` event. A `POST /cowork/confirm` resumes it.

2. **SSE for live progress.** Reuses the streaming idiom; each step emits `step_started`, `tool_call`, `tool_result`, `step_cost`, `confirmation_required`, `done`, `error`.

3. **Provider routing through gateway internals.** The agent calls the *same* `call_provider` path the Chat/Code tabs use, so spend-guard fires automatically. We do NOT bypass it. (The plan assumes `app.py` exposes a callable like `dispatch_completion(...)`. I provide a thin adapter `cowork_llm.py` that imports the existing provider adapters + spendguard exactly as the orchestrator does, matching its style.)

4. **No new dependencies.** Pure stdlib + existing FastAPI.

---

## File 1: `7ces/gateway/cowork_config.py`

```python
"""Cowork allowlist configuration.

Loads the list of directories the Cowork agent is permitted to read/write.
Deny-by-default: if the allowlist is empty, nothing is accessible.

Resolution order:
  1. COWORK_ALLOWLIST env var (os.pathsep-separated absolute paths)
  2. cowork_allowlist.json next to this file: {"allow": ["C:\\path\\one", ...]}
  3. empty list
"""
import json
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CONFIG_FILE = _HERE / "cowork_allowlist.json"


def _normalize(raw: str) -> str:
    # Canonicalize to an absolute realpath string; tolerate non-existent
    # directories by falling back to abspath (realpath of a missing path
    # still returns a normalized absolute path on 3.13).
    p = os.path.realpath(os.path.abspath(os.path.expanduser(raw)))
    return p


def load_allowlist() -> list[str]:
    raw_paths: list[str] = []

    env = os.environ.get("COWORK_ALLOWLIST", "").strip()
    if env:
        raw_paths.extend(part for part in env.split(os.pathsep) if part.strip())

    if not raw_paths and _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
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
```

---

## File 2: `7ces/gateway/coworkfs.py`

```python
"""Scoped filesystem access for the Cowork agent.

Security model (deny-by-default):
  * Every path is canonicalized with os.path.realpath (resolves symlinks,
    NTFS junctions, and reparse points to their true target) BEFORE any check.
  * We then run a belt-and-suspenders os.path.relpath check: the canonical
    path must be inside one of the canonical allowlist roots, i.e.
    os.path.relpath(target, root) must not start with '..' and must not be
    absolute (drive change on Windows).
  * For writes to a *new* file, we validate the canonical parent directory
    instead (the file itself doesn't exist yet, so realpath of the file would
    be a non-existent leaf under a real parent — we resolve the parent).
  * Any path failing these checks raises PathDenied.
"""
import os
from dataclasses import dataclass


class PathDenied(Exception):
    """Raised when a path is outside the allowlist or escapes via traversal."""


@dataclass
class ScopedFS:
    allow_roots: list[str]  # canonical absolute realpaths

    @classmethod
    def from_allowlist(cls, allowlist: list[str]) -> "ScopedFS":
        roots = [os.path.realpath(os.path.abspath(r)) for r in allowlist]
        return cls(allow_roots=roots)

    # ---- core validation -------------------------------------------------

    def _within_root(self, canonical: str) -> bool:
        for root in self.allow_roots:
            try:
                rel = os.path.relpath(canonical, root)
            except ValueError:
                # Different drive on Windows -> not within this root.
                continue
            # rel == '.' means canonical IS root (allowed).
            # rel must not climb out ('..') and must not be absolute.
            if rel == os.curdir:
                return True
            if not rel.startswith(os.pardir + os.sep) and rel != os.pardir \
                    and not os.path.isabs(rel):
                return True
        return False

    def resolve_read(self, user_path: str) -> str:
        """Canonicalize an existing path for read/list. Raises PathDenied."""
        if not self.allow_roots:
            raise PathDenied("No allowlisted directories are configured.")
        # realpath resolves symlinks/junctions to the true target.
        canonical = os.path.realpath(os.path.abspath(os.path.expanduser(user_path)))
        if not self._within_root(canonical):
            raise PathDenied(f"Path is outside the allowlist: {user_path}")
        return canonical

    def resolve_write(self, user_path: str) -> str:
        """Canonicalize a path for write/create.

        If the file exists, we resolve it directly (catches a symlink that
        points outside). If it does not exist, we resolve its PARENT directory
        (which must exist and be inside the allowlist) and join the leaf.
        """
        if not self.allow_roots:
            raise PathDenied("No allowlisted directories are configured.")

        abs_path = os.path.abspath(os.path.expanduser(user_path))

        if os.path.lexists(abs_path):
            # Resolve the real target (defeats symlink/junction escapes).
            canonical = os.path.realpath(abs_path)
            if not self._within_root(canonical):
                raise PathDenied(f"Path resolves outside the allowlist: {user_path}")
            return canonical

        parent = os.path.dirname(abs_path)
        leaf = os.path.basename(abs_path)
        if not leaf:
            raise PathDenied(f"Invalid write target: {user_path}")
        canonical_parent = os.path.realpath(parent)
        if not self._within_root(canonical_parent):
            raise PathDenied(
                f"Parent directory is outside the allowlist: {user_path}"
            )
        return os.path.join(canonical_parent, leaf)

    # ---- operations ------------------------------------------------------

    def list_dir(self, user_path: str) -> list[dict]:
        target = self.resolve_read(user_path)
        if not os.path.isdir(target):
            raise PathDenied(f"Not a directory: {user_path}")
        entries = []
        for name in sorted(os.listdir(target)):
            full = os.path.join(target, name)
            entries.append({
                "name": name,
                "is_dir": os.path.isdir(full),
                "size": os.path.getsize(full) if os.path.isfile(full) else None,
            })
        return entries

    def read_file(self, user_path: str, max_bytes: int = 200_000) -> str:
        target = self.resolve_read(user_path)
        if not os.path.isfile(target):
            raise PathDenied(f"Not a file: {user_path}")
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)

    def write_file(self, user_path: str, content: str) -> str:
        target = self.resolve_write(user_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return target

    def delete_file(self, user_path: str) -> str:
        target = self.resolve_read(user_path)  # must exist & be in-scope
        if os.path.isdir(target):
            raise PathDenied("Refusing to delete a directory.")
        os.remove(target)
        return target

    def move_file(self, src: str, dst: str) -> tuple[str, str]:
        src_c = self.resolve_read(src)       # source must exist & in-scope
        dst_c = self.resolve_write(dst)      # dest parent must be in-scope
        os.makedirs(os.path.dirname(dst_c), exist_ok=True)
        os.replace(src_c, dst_c)
        return src_c, dst_c
```

---

## File 3: `7ces/gateway/cowork_llm.py`

This adapter wires the agent into the **existing** provider + spendguard path, matching the orchestrator's import style. (Adjust the two imports marked `# MATCH ORCHESTRATOR` if `orchestrator.py` uses different symbol names — they should mirror exactly what it imports.)

```python
"""LLM dispatch for the Cowork agent.

This routes EVERY model call through the same spend-guard + provider adapters
used by the Chat and Code tabs, so dollar caps are enforced before each paid
call and cost is metered identically.

Mirrors the import pattern in orchestrator.py.
"""
from providers import anthropic as anthropic_provider   # MATCH ORCHESTRATOR
from providers import deepseek as deepseek_provider     # MATCH ORCHESTRATOR
import spendguard


# Provider/model routing identical in spirit to the Code tab defaults.
DEFAULT_PLANNER = ("anthropic", "claude-opus")
DEFAULT_EXECUTOR = ("deepseek", "deepseek-v4-pro")


def _adapter(provider: str):
    if provider == "anthropic":
        return anthropic_provider
    if provider == "deepseek":
        return deepseek_provider
    raise ValueError(f"Unknown provider: {provider}")


def complete(provider: str, model: str, messages: list[dict],
             *, max_tokens: int = 2048, temperature: float = 0.2) -> dict:
    """Single completion through the spend-guard.

    Returns: {"text": str, "cost": float, "provider": str, "model": str,
              "input_tokens": int, "output_tokens": int}
    """
    adapter = _adapter(provider)

    # 1) Pre-flight estimate + cap enforcement (spend-guard BEFORE paid call).
    est = adapter.estimate_cost(model=model, messages=messages,
                                max_tokens=max_tokens)
    spendguard.check_or_raise(est)  # raises spendguard.CapExceeded if over cap

    # 2) Make the paid call.
    result = adapter.complete(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # 3) Meter the ACTUAL cost.
    actual = result.get("cost", est)
    spendguard.record(actual)

    return {
        "text": result.get("text", ""),
        "cost": actual,
        "provider": provider,
        "model": model,
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
    }
```

> **Integration note:** If `orchestrator.py` does not call `estimate_cost` / `check_or_raise` / `record` / `complete` by these exact names, copy the *exact* spend-guard sequence from `orchestrator.py` into `complete()` so behavior matches and the 41 tests stay green. The three obligations that must hold: estimate → cap-check → paid call → record actual.

---

## File 4: `7ces/gateway/cowork_tools.py`

```python
"""Tool registry for the Cowork agent.

Each tool declares whether it is destructive, its risk level, and produces an
'affected_paths' preview used by the confirmation dialog. Read-only tools run
immediately; destructive tools are gated.
"""
from dataclasses import dataclass
from typing import Callable

from coworkfs import ScopedFS, PathDenied


@dataclass
class ToolSpec:
    name: str
    description: str
    destructive: bool
    risk: str  # "none" | "low" | "medium" | "high"
    args_schema: dict


TOOLS: dict[str, ToolSpec] = {
    "list_dir": ToolSpec(
        "list_dir", "List entries in an allowlisted directory.",
        destructive=False, risk="none",
        args_schema={"path": "string"},
    ),
    "read_file": ToolSpec(
        "read_file", "Read a UTF-8 text file within the allowlist.",
        destructive=False, risk="none",
        args_schema={"path": "string"},
    ),
    "write_file": ToolSpec(
        "write_file", "Create or overwrite a file within the allowlist.",
        destructive=True, risk="medium",
        args_schema={"path": "string", "content": "string"},
    ),
    "delete_file": ToolSpec(
        "delete_file", "Delete a file within the allowlist.",
        destructive=True, risk="high",
        args_schema={"path": "string"},
    ),
    "move_file": ToolSpec(
        "move_file", "Move/rename a file within the allowlist.",
        destructive=True, risk="medium",
        args_schema={"src": "string", "dst": "string"},
    ),
    "finish": ToolSpec(
        "finish", "Declare the task complete with a summary.",
        destructive=False, risk="none",
        args_schema={"summary": "string"},
    ),
}


def tool_catalog_text() -> str:
    """Human/LLM-readable catalog injected into the planner prompt."""
    lines = ["Available tools (respond with exactly one JSON object):"]
    for spec in TOOLS.values():
        flag = "DESTRUCTIVE" if spec.destructive else "read-only"
        lines.append(
            f'- {spec.name} ({flag}, risk={spec.risk}): {spec.description} '
            f'args={spec.args_schema}'
        )
    return "\n".join(lines)


def preview_affected(tool: str, args: dict, fs: ScopedFS) -> dict:
    """Build a confirmation preview WITHOUT executing the operation."""
    spec = TOOLS.get(tool)
    if not spec:
        return {"affected": [], "risk": "unknown", "summary": f"Unknown tool {tool}"}

    affected: list[str] = []
    summary = ""
    try:
        if tool == "write_file":
            target = fs.resolve_write(args.get("path", ""))
            affected = [target]
            exists = __import__("os").path.exists(target)
            summary = (f"{'Overwrite' if exists else 'Create'} file: {target} "
                       f"({len(args.get('content',''))} chars)")
        elif tool == "delete_file":
            target = fs.resolve_read(args.get("path", ""))
            affected = [target]
            summary = f"Permanently delete file: {target}"
        elif tool == "move_file":
            src = fs.resolve_read(args.get("src", ""))
            dst = fs.resolve_write(args.get("dst", ""))
            affected = [src, dst]
            summary = f"Move {src} -> {dst}"
    except PathDenied as e:
        return {"affected": [], "risk": "blocked", "summary": str(e),
                "denied": True}

    return {"affected": affected, "risk": spec.risk, "summary": summary}


def execute(tool: str, args: dict, fs: ScopedFS) -> dict:
    """Execute a tool. Raises PathDenied / ValueError on bad input."""
    if tool == "list_dir":
        return {"entries": fs.list_dir(args["path"])}
    if tool == "read_file":
        return {"content": fs.read_file(args["path"])}
    if tool == "write_file":
        path = fs.write_file(args["path"], args.get("content", ""))
        return {"written": path}
    if tool == "delete_file":
        path = fs.delete_file(args["path"])
        return {"deleted": path}
    if tool == "move_file":
        src, dst = fs.move_file(args["src"], args["dst"])
        return {"moved_from": src, "moved_to": dst}
    if tool == "finish":
        return {"finished": True, "summary": args.get("summary", "")}
    raise ValueError(f"Unknown tool: {tool}")
```

---

## File 5: `7ces/gateway/cowork.py`

```python
"""Cowork agent engine: plan -> act -> observe -> reflect.

State machine with confirmation gating. Because a destructive tool must pause
for user confirmation, the loop is driven step-by-step by the web layer:

  start()    -> creates a session, runs first plan, returns next action.
  step()     -> if pending action is read-only, execute & re-plan.
                if destructive, return confirmation_required and pause.
  confirm()  -> approve (execute pending) or reject (skip & re-plan).

Each session keeps a transcript and a running cost total.
"""
import json
import re
import uuid

import cowork_llm
import cowork_tools
from cowork_config import load_allowlist
from coworkfs import ScopedFS, PathDenied

MAX_STEPS = 25

_SESSIONS: dict[str, "CoworkSession"] = {}


def _extract_json(text: str) -> dict:
    """Pull the first JSON object from a model response."""
    text = text.strip()
    # Strip code fences if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object in model response.")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("Unbalanced JSON in model response.")


PLANNER_SYSTEM = """You are the Cowork agent. You solve the user's task by \
choosing ONE tool per step. Think briefly, then output a single JSON object:
{"thought": "...", "tool": "<tool_name>", "args": { ... }}

Rules:
- Only use the tools listed.
- Use read-only tools (list_dir, read_file) to gather context first.
- Only use destructive tools when necessary; they require user confirmation.
- When the task is done, use the "finish" tool with a summary.
- All file paths must be inside the allowlisted directories.
"""


class CoworkSession:
    def __init__(self, task: str, planner: tuple[str, str],
                 executor: tuple[str, str]):
        self.id = uuid.uuid4().hex
        self.task = task
        self.planner = planner
        self.executor = executor
        self.fs = ScopedFS.from_allowlist(load_allowlist())
        self.transcript: list[dict] = []   # observations fed back to planner
        self.history: list[dict] = []       # UI step log
        self.total_cost = 0.0
        self.step_index = 0
        self.pending: dict | None = None     # awaiting confirmation
        self.done = False
        self.summary = ""

    # ---- prompt construction --------------------------------------------

    def _messages(self) -> list[dict]:
        allow = "\n".join(self.fs.allow_roots) or "(none configured)"
        context = [
            f"TASK:\n{self.task}",
            f"ALLOWLISTED DIRECTORIES:\n{allow}",
            cowork_tools.tool_catalog_text(),
        ]
        if self.transcript:
            obs = "\n".join(
                f"Step {o['step']}: {o['tool']}({json.dumps(o['args'])}) -> "
                f"{json.dumps(o['result'])[:600]}"
                for o in self.transcript
            )
            context.append("OBSERVATIONS SO FAR:\n" + obs)
        context.append("Choose the next tool now.")
        return [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": "\n\n".join(context)},
        ]

    # ---- planning --------------------------------------------------------

    def _plan_next(self) -> list[dict]:
        """Call the planner model. Returns a list of UI events."""
        events = []
        if self.step_index >= MAX_STEPS:
            self.done = True
            self.summary = "Reached max steps."
            events.append({"type": "done", "summary": self.summary,
                           "total_cost": round(self.total_cost, 6)})
            return events

        self.step_index += 1
        events.append({"type": "step_started", "step": self.step_index})

        provider, model = self.planner
        comp = cowork_llm.complete(provider, model, self._messages())
        self.total_cost += comp["cost"]
        events.append({
            "type": "step_cost", "step": self.step_index,
            "cost": round(comp["cost"], 6),
            "total_cost": round(self.total_cost, 6),
            "provider": provider, "model": model,
        })

        try:
            decision = _extract_json(comp["text"])
        except ValueError as e:
            self.done = True
            self.summary = f"Planner produced invalid output: {e}"
            events.append({"type": "error", "message": self.summary})
            return events

        tool = decision.get("tool", "")
        args = decision.get("args", {}) or {}
        thought = decision.get("thought", "")

        events.append({"type": "plan", "step": self.step_index,
                       "thought": thought, "tool": tool, "args": args})

        spec = cowork_tools.TOOLS.get(tool)
        if not spec:
            # Feed error back and let it re-plan.
            self.transcript.append({"step": self.step_index, "tool":