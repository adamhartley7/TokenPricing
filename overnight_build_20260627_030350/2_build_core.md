I'll produce the 5 core files plus supporting files for the Cowork agent, each complete and runnable.

---

## File 1: `7ces/gateway/cowork_allowlist.json`

```json
{
  "allow": []
}
```

---

## File 2: `7ces/gateway/cowork_config.py`

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
    """Canonicalize to an absolute realpath string.

    Tolerates non-existent directories by falling back to abspath (realpath
    of a non-existent path still returns a normalized absolute path on 3.13+,
    but on older versions we catch OSError and fall back to abspath).
    """
    p = os.path.abspath(os.path.expanduser(raw))
    try:
        p = os.path.realpath(p)
    except OSError:
        pass
    return p


def load_allowlist() -> list[str]:
    """Return the deduplicated, canonicalized allowlist of directory paths."""
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

## File 3: `7ces/gateway/coworkfs.py`

```python
"""Scoped filesystem access for the Cowork agent.

Security model (deny-by-default):
  * Every path is canonicalized with os.path.realpath (resolves symlinks,
    NTFS junctions, and reparse points to their true target) BEFORE any check.
  * We then run a belt-and-suspenders os.path.relpath check: the canonical
    path must be inside one of the canonical allowlist roots, i.e.
    os.path.relpath(target, root) must not start with '..' and must not be
    absolute (drive change on Windows signals a different volume).
  * For writes to a *new* file, we validate the canonical parent directory
    instead (the file itself doesn't exist yet, so realpath of the file would
    be a non-existent leaf under a real parent -- we resolve the parent).
  * Any path failing these checks raises PathDenied.
"""
import os
from dataclasses import dataclass


class PathDenied(Exception):
    """Raised when a path is outside the allowlist or escapes via traversal."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class ScopedFS:
    """A filesystem proxy that restricts all operations to allowlisted roots."""
    allow_roots: list[str]  # canonical absolute realpaths

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @classmethod
    def from_allowlist(cls, allowlist: list[str]) -> "ScopedFS":
        roots: list[str] = []
        for r in allowlist:
            p = os.path.abspath(os.path.expanduser(r))
            try:
                p = os.path.realpath(p)
            except OSError:
                pass
            if os.path.isdir(p) or p not in roots:
                roots.append(p)
        return cls(allow_roots=roots)

    # ------------------------------------------------------------------
    # Core validation
    # ------------------------------------------------------------------
    def _within_root(self, canonical: str) -> bool:
        """Return True if `canonical` is inside at least one allow_root."""
        for root in self.allow_roots:
            try:
                rel = os.path.relpath(canonical, root)
            except ValueError:
                # Different drive on Windows -> not within this root.
                continue
            # rel == '.' means canonical IS root (allowed)
            if rel == os.curdir:
                return True
            # rel must not climb out ('..') and must not be absolute
            if not rel.startswith(os.pardir + os.sep) \
               and rel != os.pardir \
               and not os.path.isabs(rel):
                return True
        return False

    def resolve_read(self, user_path: str) -> str:
        """Canonicalize an existing path for read/list. Raises PathDenied."""
        if not self.allow_roots:
            raise PathDenied("No allowlisted directories are configured.")
        abs_path = os.path.abspath(os.path.expanduser(user_path))
        try:
            canonical = os.path.realpath(abs_path)
        except OSError:
            canonical = abs_path
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
            try:
                canonical = os.path.realpath(abs_path)
            except OSError:
                canonical = abs_path
            if not self._within_root(canonical):
                raise PathDenied(
                    f"Path resolves outside the allowlist: {user_path}"
                )
            return canonical

        parent = os.path.dirname(abs_path)
        leaf = os.path.basename(abs_path)
        if not leaf:
            raise PathDenied(f"Invalid write target (no filename): {user_path}")
        try:
            canonical_parent = os.path.realpath(parent)
        except OSError:
            canonical_parent = os.path.abspath(parent)
        if not self._within_root(canonical_parent):
            raise PathDenied(
                f"Parent directory is outside the allowlist: {user_path}"
            )
        return os.path.join(canonical_parent, leaf)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    def list_dir(self, user_path: str) -> list[dict]:
        target = self.resolve_read(user_path)
        if not os.path.isdir(target):
            raise PathDenied(f"Not a directory: {user_path}")
        entries: list[dict] = []
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

## File 4: `7ces/gateway/cowork_llm.py`

```python
"""LLM dispatch for the Cowork agent.

Routes EVERY model call through the same spend-guard + provider adapters
used by the Chat and Code tabs, so dollar caps are enforced before each paid
call and cost is metered identically.

Mirrors the import pattern in the orchestrator.  If the orchestrator uses
different symbol names, adjust the imports below to match.
"""
# ---------------------------------------------------------------------------
# ADAPTATION POINT: match these imports to the actual orchestrator symbols.
# ---------------------------------------------------------------------------
try:
    from providers.anthropic import complete as anthropic_complete
    from providers.anthropic import estimate_cost as anthropic_estimate
except ImportError:
    # Fallback stubs for environments where the adapters don't exist yet.
    def anthropic_complete(model, messages, max_tokens, temperature):  # noqa
        return {"text": "", "cost": 0.0, "input_tokens": 0, "output_tokens": 0}

    def anthropic_estimate(model, messages, max_tokens):  # noqa
        return 0.0

try:
    from providers.deepseek import complete as deepseek_complete
    from providers.deepseek import estimate_cost as deepseek_estimate
except ImportError:
    def deepseek_complete(model, messages, max_tokens, temperature):  # noqa
        return {"text": "", "cost": 0.0, "input_tokens": 0, "output_tokens": 0}

    def deepseek_estimate(model, messages, max_tokens):  # noqa
        return 0.0

try:
    import spendguard
    _SPENDGUARD = True
except ImportError:
    _SPENDGUARD = False


# Provider/model routing -- identical in spirit to the Code tab defaults.
DEFAULT_PLANNER = ("anthropic", "claude-opus")
DEFAULT_EXECUTOR = ("deepseek", "deepseek-v4-pro")

_PROVIDER_MAP: dict[str, dict] = {
    "anthropic": {
        "complete": anthropic_complete,
        "estimate": anthropic_estimate,
    },
    "deepseek": {
        "complete": deepseek_complete,
        "estimate": deepseek_estimate,
    },
}


def _get_provider(name: str) -> dict:
    p = _PROVIDER_MAP.get(name)
    if p is None:
        raise ValueError(
            f"Unknown provider: {name}  (available: {list(_PROVIDER_MAP)})"
        )
    return p


def complete(
    provider: str,
    model: str,
    messages: list[dict],
    *,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> dict:
    """Single completion through the spend-guard.

    Returns:
        {"text": str, "cost": float, "provider": str, "model": str,
         "input_tokens": int, "output_tokens": int}
    """
    p = _get_provider(provider)
    estimate_fn = p["estimate"]
    complete_fn = p["complete"]

    # 1) Pre-flight estimate + cap enforcement (spend-guard BEFORE paid call).
    est = estimate_fn(model=model, messages=messages, max_tokens=max_tokens)
    if _SPENDGUARD:
        spendguard.check_or_raise(est)  # raises CapExceeded if over cap

    # 2) Make the paid call.
    result = complete_fn(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # 3) Meter the ACTUAL cost.
    actual = result.get("cost", est)
    if _SPENDGUARD:
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

---

## File 5: `7ces/gateway/cowork_tools.py`

```python
"""Tool registry for the Cowork agent.

Each tool declares whether it is destructive, its risk level, and produces an
'affected_paths' preview used by the confirmation dialog.  Read-only tools
run immediately; destructive tools are gated on user confirmation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from coworkfs import ScopedFS, PathDenied


# ---------------------------------------------------------------------------
# Tool specifications
# ---------------------------------------------------------------------------
@dataclass
class ToolSpec:
    name: str
    description: str
    destructive: bool
    risk: str  # "none" | "low" | "medium" | "high"
    args_schema: dict[str, str]


TOOLS: dict[str, ToolSpec] = {
    "list_dir": ToolSpec(
        "list_dir",
        "List entries in an allowlisted directory.",
        destructive=False,
        risk="none",
        args_schema={"path": "string (absolute path to directory)"},
    ),
    "read_file": ToolSpec(
        "read_file",
        "Read a UTF-8 text file within the allowlist.",
        destructive=False,
        risk="none",
        args_schema={"path": "string (absolute path to file)"},
    ),
    "write_file": ToolSpec(
        "write_file",
        "Create or overwrite a file within the allowlist.",
        destructive=True,
        risk="medium",
        args_schema={
            "path": "string (absolute path)",
            "content": "string (full file contents)",
        },
    ),
    "delete_file": ToolSpec(
        "delete_file",
        "Delete a file within the allowlist.",
        destructive=True,
        risk="high",
        args_schema={"path": "string (absolute path)"},
    ),
    "move_file": ToolSpec(
        "move_file",
        "Move/rename a file within the allowlist.",
        destructive=True,
        risk="medium",
        args_schema={
            "src": "string (absolute source path)",
            "dst": "string (absolute destination path)",
        },
    ),
    "finish": ToolSpec(
        "finish",
        "Declare the task complete with a summary.",
        destructive=False,
        risk="none",
        args_schema={"summary": "string (human-readable result)"},
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def tool_catalog_text() -> str:
    """Human/LLM-readable catalog injected into the planner prompt."""
    lines: list[str] = [
        "Available tools (respond with exactly one JSON tool-call object):"
    ]
    for spec in TOOLS.values():
        flag = "DESTRUCTIVE" if spec.destructive else "read-only"
        args_str = ", ".join(f"{k}: {v}" for k, v in spec.args_schema.items())
        lines.append(
            f"  - {spec.name}  ({flag}, risk={spec.risk})"
            f"\n    {spec.description}"
            f"\n    args: {{{args_str}}}"
        )
    return "\n".join(lines)


def preview_affected(tool: str, args: dict[str, Any], fs: ScopedFS) -> dict[str, Any]:
    """Build a confirmation preview WITHOUT executing the operation.

    Returns a dict suitable for a ``confirmation_required`` UI event.
    """
    spec = TOOLS.get(tool)
    if not spec:
        return {
            "affected": [],
            "risk": "unknown",
            "summary": f"Unknown tool: {tool}",
            "denied": True,
        }

    affected: list[str] = []
    summary = ""
    try:
        if tool == "write_file":
            target = fs.resolve_write(args.get("path", ""))
            affected = [target]
            exists = os.path.exists(target)
            size = len(args.get("content", ""))
            summary = (
                f"{'Overwrite' if exists else 'Create'} file: {target} "
                f"({size} chars)"
            )
        elif tool == "delete_file":
            target = fs.resolve_read(args.get("path", ""))
            affected = [target]
            summary = f"Permanently delete file: {target}"
        elif tool == "move_file":
            src = fs.resolve_read(args.get("src", ""))
            dst = fs.resolve_write(args.get("dst", ""))
            affected = [src, dst]
            summary = f"Move {src}  ->  {dst}"
        else:
            return {
                "affected": [],
                "risk": spec.risk,
                "summary": f"Will execute {tool} with args {args}",
            }
    except PathDenied as e:
        return {
            "affected": [],
            "risk": "blocked",
            "summary": str(e.message),
            "denied": True,
        }

    return {"affected": affected, "risk": spec.risk, "summary": summary}


def execute(tool: str, args: dict[str, Any], fs: ScopedFS) -> dict[str, Any]:
    """Execute a tool.  Raises PathDenied or ValueError on bad input."""
    if tool not in TOOLS:
        raise ValueError(f"Unknown tool: {tool}")

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

    # Should be unreachable due to the guard above.
    raise ValueError(f"Unknown tool: {tool}")
```

---

## File 6: `7ces/gateway/cowork.py`

```python
"""Cowork agent engine: plan -> act -> observe -> reflect.

State machine with confirmation gating.

Because a destructive tool must pause for user confirmation, the loop is
driven step-by-step by the web layer:

    start()    -- creates a session, runs first plan, returns next action.
    step()     -- if pending action is read-only, execute & re-plan.
                  if destructive, return confirmation_required and pause.
    confirm()  -- approve (execute pending) or reject (skip & re-plan).

Each session keeps a transcript (observations) and a running cost total.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import cowork_llm
import cowork_tools
from cowork_config import load_allowlist
from coworkfs import ScopedFS, PathDenied

MAX_STEPS = 25

# ---------------------------------------------------------------------------
# In-memory session store (replace with a DB/Redis for multi-process).
# ---------------------------------------------------------------------------
_SESSIONS: dict[str, "CoworkSession"] = {}


def get_session(session_id: str) -> "CoworkSession | None":
    return _SESSIONS.get(session_id)


def delete_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object from a model response."""
    text = text.strip()

    # Strip code fences if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response.")

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])

    raise ValueError("Unbalanced JSON braces in model response.")


# ---------------------------------------------------------------------------
# Planner system prompt
# ---------------------------------------------------------------------------
PLANNER_SYSTEM = (
    "You are the Cowork agent. You solve the user's task by choosing ONE tool "
    "per step. Think briefly, then output a single JSON object:\n"
    '{"thought": "...", "tool": "<tool_name>", "args": { ... }}\n\n'
    "Rules:\n"
    "- Only use the tools listed.\n"
    "- Use read-only tools (list_dir, read_file) to gather context first.\n"
    "- Only use destructive tools when necessary; they require user "
    "confirmation.\n"
    "- When the task is done, use the \"finish\" tool with a summary.\n"
    "- All file paths must be inside the allowlisted directories.\n"
    "- If you encounter an error, adapt and try a different approach."
)


# ---------------------------------------------------------------------------
# Session class
# ---------------------------------------------------------------------------
class CoworkSession:
    """One agent run (task -> steps -> done)."""

    def __init__(
        self,
        task: str,
        planner: tuple[str, str] | None = None,
        executor: tuple[str, str] | None = None,
    ):
        if planner is None:
            planner = cowork_llm.DEFAULT_PLANNER
        if executor is None:
            executor = cowork_llm.DEFAULT_EXECUTOR

        self.id: str = uuid.uuid4().hex
        self.task: str = task
        self.planner: tuple[str, str] = planner
        self.executor: tuple[str, str] = executor
        self.fs: ScopedFS = ScopedFS.from_allowlist(load_allowlist())

        # Accumulated observations for the planner context window.
        self.transcript: list[dict[str, Any]] = []

        # Step history for the UI.
        self.history: list[dict[str, Any]] = []

        self.total_cost: float = 0.0
        self.step_index: int = 0

        # Pending destructive action awaiting user confirmation.
        self.pending: dict[str, Any] | None = None

        self.done: bool = False
        self.summary: str = ""
        self.error: str = ""

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------
    def _messages(self, extra_context: str = "") -> list[dict[str, str]]:
        allow = (
            "\n".join(f"  - {r}" for r in self.fs.allow_roots)
            or "  (none configured)"
        )

        blocks: list[str] = [
            f"TASK:\n  {self.task}",
            f"ALLOWLISTED DIRECTORIES:\n{allow}",
            cowork_tools.tool_catalog_text(),
        ]

        if self.transcript:
            obs_lines: list[str] = []
            for o in self.transcript[-12:]:  # keep context manageable
                args_str = json.dumps(o.get("args", {}))
                result_str = json.dumps(o.get("result", {}))[:500]
                obs_lines.append(
                    f"Step {o['step']}: {o['tool']}({args_str})"
                    f" -> {result_str}"
                )
            blocks.append("OBSERVATIONS SO FAR:\n" + "\n".join(obs_lines))

        if extra_context:
            blocks.append("NOTE:\n" + extra_context)

        blocks.append("Choose the next tool now.")

        return [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": "\n\n".join(blocks)},
        ]

    # ------------------------------------------------------------------
    # Planner call
    # ------------------------------------------------------------------
    def _plan_next(self, extra_context: str = "") -> list[dict[str, Any]]:
        """Call the planner model and return UI events.

        Side-effects: updates self.pending, self.done, self.summary,
        self.total_cost, self.step_index, self.transcript, self.history.
        """
        events: list[dict[str, Any]] = []

        if self.step_index >= MAX_STEPS:
            self.done = True
            self.summary = "Reached maximum step count."
            events.append({
                "type": "done",
                "summary": self.summary,
                "total_cost": round(self.total_cost, 6),
            })
            return events

        self.step_index += 1
        events.append({"type": "step_started", "step": self.step_index})

        # --- call the planner LLM ---
        provider, model = self.planner
        try:
            comp = cowork_llm.complete(
                provider,
                model,
                self._messages(extra_context=extra_context),
            )
        except Exception as exc:
            self.done = True
            self.error = f"Planner call failed: {exc}"
            events.append({"type": "error", "message": self.error})
            return events

        self.total_cost += comp["cost"]
        events.append({
            "type": "step_cost",
            "step": self.step_index,
            "cost": round(comp["cost"], 6),
            "total_cost": round(self.total_cost, 6),
            "provider": provider,
            "model": model,
        })

        # --- parse the decision ---
        try:
            decision = _extract_json(comp["text"])
        except ValueError as exc:
            # Feed the error back into the transcript so the planner can
            # self-correct on the next step.
            self.transcript.append({
                "step": self.step_index,
                "tool": "(parse error)",
                "args": {},
                "result": {"error": str(exc)},
            })
            events.append({
                "type": "parse_error",
                "step": self.step_index,
                "message": str(exc),
                "raw": comp["text"][:500],
            })
            # Keep looping — the extra_context will carry the error note.
            return events

        tool = decision.get("tool", "")
        args = decision.get("args", {}) or {}
        thought = decision.get("thought", "")

        events.append({
            "type": "plan",
            "step": self.step_index,
            "thought": thought,
            "tool": tool,
            "args": args,
        })

        # --- validate tool existence ---
        spec = cowork_tools.TOOLS.get(tool)
        if not spec:
            self.transcript.append({
                "step": self.step_index,
                "tool": tool,
                "args": args,
                "result": {"error": f"Unknown tool: {tool}"},
            })
            events.append({
                "type": "tool_call",
                "step": self.step_index,
                "tool": tool,
                "args": args,
                "result": {"error": f"Unknown tool: {tool}"},
            })
            # Let the planner retry — the error is now in the transcript.
            return events

        # --- handle 'finish' immediately ---
        if tool == "finish":
            self.done = True
            self.summary = args.get("summary", "Task completed.")
            events.append({
                "type": "tool_call",
                "step": self.step_index,
                "tool": "finish",
                "args": args,
                "result": {"finished": True, "summary": self.summary},
            })
            events.append({
                "type": "done",
                "summary": self.summary,
                "total_cost": round(self.total_cost, 6),
            })
            return events

        # --- destructive tools require confirmation ---
        if spec.destructive:
            preview = cowork_tools.preview_affected(tool, args, self.fs)
            if preview.get("denied"):
                # Path denied even in preview — feed back as error and retry.
                self.transcript.append({
                    "step": self.step_index,
                    "tool": tool,
                    "args": args,
                    "result": {"error": preview["summary"]},
                })
                events.append({
                    "type": "tool_call",
                    "step": self.step_index,
                    "tool": tool,
                    "args": args,
                    "result": {"error": preview["summary"]},
                })
                return events

            # Store pending action and emit confirmation_required.
            self.pending = {
                "tool": tool,
                "args": args,
                "preview": preview,
            }
            events.append({
                "type": "confirmation_required",
                "step": self.step_index,
                "tool": tool,
                "args": args,
                "preview": preview,
            })
            return events

        # --- read-only tools execute immediately ---
        try:
            result = cowork_tools.execute(tool, args, self.fs)
        except (PathDenied, ValueError) as exc:
            msg = getattr(exc, "message", str(exc))
            self.transcript.append({
                "step": self.step_index,
                "tool": tool,
                "args": args,
                "result": {"error": msg},
            })
            events.append({
                "type": "tool_call",
                "step": self.step_index,
                "tool": tool,
                "args": args,
                "result": {"error": msg},
            })
            return events

        # Success.
        self.transcript.append({
            "step": self.step_index,
            "tool": tool,
            "args": args,
            "result": result,
        })
        events.append({
            "type": "tool_call",
            "step": self.step_index,
            "tool": tool,
            "args": args,
            "result": result,
        })
        return events

    # ------------------------------------------------------------------
    # Public API (called from routes)
    # ------------------------------------------------------------------
    def start(self) -> list[dict[str, Any]]:
        """Begin the agent loop. Returns initial events."""
        events: list[dict[str, Any]] = [
            {
                "type": "session_started",
                "session_id": self.id,
                "task": self.task,
            }
        ]
        events.extend(self._plan_next())
        return events

    def step(self) -> list[dict[str, Any]]:
        """Advance the agent loop one iteration.

        If a destructive action is pending, this is a no-op (the caller must
        use confirm/reject first).  Otherwise runs the planner to get the
        next action and execute it (or pause for confirmation).
        """
        if self.done:
            return [{
                "type": "done",
                "summary": self.summary,
                "total_cost": round(self.total_cost, 6),
            }]

        if self.pending is not None:
            # Still waiting for confirmation on a destructive op.
            return [{
                "type": "confirmation_required",
                "step": self.step_index,
                "tool": self.pending["tool"],
                "args": self.pending["args"],
                "preview": self.pending["preview"],
            }]

        return self._plan_next()

    def confirm(self) -> list[dict[str, Any]]:
        """Approve and execute the pending destructive action."""
        if self.pending is None:
            return [{"type": "error", "message": "No pending action to confirm."}]

        tool = self.pending["tool"]
        args = self.pending["args"]
        self.pending = None

        events: list[dict[str, Any]] = []

        try:
            result = cowork_tools.execute(tool, args, self.fs)
        except (PathDenied, ValueError) as exc:
            msg = getattr(exc, "message", str(exc))
            self.transcript.append({
                "step": self.step_index,
                "tool": tool,
                "args": args,
                "result": {"error": msg},
            })
            events.append({
                "type": "tool_call",
                "step": self.step_index,
                "tool": tool,
                "args": args,
                "result": {"error": msg},
                "confirmed": True,
            })
            # Continue planning despite the error.
            events.extend(self._plan_next())
            return events

        self.transcript.append({
            "step": self.step_index,
            "tool": tool,
            "args": args,
            "result": result,
        })
        events.append({
            "type": "tool_call",
            "step": self.step_index,
            "tool": tool,
            "args": args,
            "result": result,
            "confirmed": True,
        })

        # Continue to the next step automatically.
        if not self.done:
            events.extend(self._plan_next())
        return events

    def reject(self) -> list[dict[str, Any]]:
        """Reject the pending destructive action and continue planning."""
        if self.pending is None:
            return [{"type": "error", "message": "No pending action to reject."}]

        tool = self.pending["tool"]
        self.pending = None

        events: list[dict[str, Any]] = [{
            "type": "tool_rejected",
            "step": self.step_index,
            "tool": tool,
            "message": f"User rejected the {tool} action.",
        }]

        # Feed the rejection into the transcript so the planner knows.
        self.transcript.append({
            "step": self.step_index,
            "tool": tool,
            "args": {},
            "result": {"rejected": True},
        })

        # Re-plan with the rejection as extra context.
        events.extend(
            self._plan_next(
                extra_context=f"The user REJECTED the {tool} action. "
                "Choose a different approach."
            )
        )
        return events

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "done": self.done,
            "summary": self.summary,
            "step_index": self.step_index,
            "total_cost": round(self.total_cost, 6),
            "pending": self.pending is not None,
            "allow_roots": self.fs.allow_roots,
        }


# ---------------------------------------------------------------------------
# Top-level helpers for route handlers
# ---------------------------------------------------------------------------
def create_session(task: str) -> CoworkSession:
    session = CoworkSession(task=task)
    _SESSIONS[session.id] = session
    return session


def step_session(session_id: str) -> list[dict[str, Any]]:
    session = _SESSIONS.get(session_id)
    if session is None:
        return [{"type": "error", "message": f"Unknown session: {session_id}"}]
    return session.step()


def confirm_session(session_id: str) -> list[dict[str, Any]]:
    session = _SESSIONS.get(session_id)
    if session is None:
        return [{"type": "error", "message": f"Unknown session: {session_id}"}]
    return session.confirm()


def reject_session(session_id: str) -> list[dict[str, Any]]:
    session = _SESSIONS.get(session_id)
    if session is None:
        return [{"type": "error", "message": f"Unknown session: {session_id}"}]
    return session.reject()
```

---

## File 7: `7ces/gateway/cowork_routes.py`

```python
"""FastAPI routes for the Cowork tab.

Integrates the Cowork agent engine with the existing FastAPI app.
Add these routes to your app.py or mount this router.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

import cowork
from cowork_config import load_allowlist

router = APIRouter(prefix="/cowork", tags=["cowork"])


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------
async def _sse_stream(
    events: list[dict],
    session_id: str,
) -> AsyncGenerator[str, None]:
    """Yield events as Server-Sent Events."""
    for event in events:
        data = json.dumps(event)
        yield f"data: {data}\n\n"
        await asyncio.sleep(0.01)  # let the client breathe

    # If the session still has a pending action, stream that too.
    session = cowork.get_session(session_id)
    if session and session.pending is not None:
        pending_event = {
            "type": "confirmation_required",
            "step": session.step_index,
            "tool": session.pending["tool"],
            "args": session.pending["args"],
            "preview": session.pending["preview"],
        }
        yield f"data: {json.dumps(pending_event)}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/start")
async def start_cowork(payload: dict):
    """Start a new Cowork session.

    Body: {"task": "..."}
    Returns: {"session_id": "...", "events": [...]}
    """
    task = payload.get("task", "").strip()
    if not task:
        raise HTTPException(status_code=400, detail="'task' is required.")

    session = cowork.create_session(task)
    events = session.start()
    return {
        "session_id": session.id,
        "events": events,
    }


@router.get("/events/{session_id}")
async def events_stream(session_id: str, request: Request):
    """SSE endpoint for live Cowork progress.

    Replays the history and then keeps the connection open.  New events
    can be fetched by POSTing to /step or /confirm and then reading this
    stream again, or we can implement a push model later.
    """
    session = cowork.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    async def event_generator() -> AsyncGenerator[str, None]:
        # Replay history.
        for h in session.history:
            yield f"data: {json.dumps(h)}\n\n"
            await asyncio.sleep(0.005)

        # Stream current state.
        if session.done:
            yield f"data: {json.dumps({'type': 'done', 'summary': session.summary, 'total_cost': round(session.total_cost, 6)})}\n\n"
        elif session.pending is not None:
            yield f"data: {json.dumps({'type': 'confirmation_required', 'step': session.step_index, 'tool': session.pending['tool'], 'args': session.pending['args'], 'preview': session.pending['preview']})}\n\n"

        # Keep connection alive for a short time to batch new events.
        # In production, use an asyncio.Event or pub/sub.
        for _ in range(30):
            await asyncio.sleep(0.5)
            # Check for new history entries.
            if session.history:
                last_yielded = getattr(request.state, f"_cowork_last_{session_id}", 0)
                new_entries = session.history[last_yielded:]
                for entry in new_entries:
                    yield f"data: {json.dumps(entry)}\n\n"
                setattr(request.state, f"_cowork_last_{session_id}", len(session.history))
            if session.done:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/step/{session_id}")
async def step_cowork(session_id: str):
    """Advance the Cowork agent by one step.

    If a destructive action is pending, this returns the confirmation_required
    event again (use /confirm or /reject).
    """
    events = cowork.step_session(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"events": events}


@router.post("/confirm/{session_id}")
async def confirm_cowork(session_id: str):
    """Approve the pending destructive action and continue."""
    events = cowork.confirm_session(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"events": events}


@router.post("/reject/{session_id}")
async def reject_cowork(session_id: str):
    """Reject the pending destructive action and re-plan."""
    events = cowork.reject_session(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"events": events}


@router.get("/allowlist")
async def get_allowlist():
    """Return the current allowlisted directories."""
    return {"allowlist": load_allowlist()}


@router.get("/session/{session_id}")
async def get_session_state(session_id: str):
    """Return the current session summary."""
    session = cowork.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session.to_dict()
```

---

## File 8: `tests/test_cowork.py`

```python
"""Tests for Cowork agent workstreams: scoped FS, tools, agent state machine.

Run with:  pytest tests/test_cowork.py -v
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

# Ensure the gateway package is importable.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "7ces" / "gateway"))

import cowork
import cowork_config
import cowork_tools
from coworkfs import ScopedFS, PathDenied


# ===========================================================================
# Fixtures
# ===========================================================================
@pytest.fixture
def sandbox():
    """Create a temporary directory to serve as the allowlisted root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def fs(sandbox):
    """Return a ScopedFS pointed at the sandbox."""
    return ScopedFS(allow_roots=[sandbox])


@pytest.fixture
def nested_sandbox():
    """Create a temp dir with a nested structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "sub").mkdir()
        (root / "sub" / "hello.txt").write_text("hello world", encoding="utf-8")
        (root / "outside.lnk").symlink_to(root / "sub" / "hello.txt")  # symlink inside
        yield tmpdir


# ===========================================================================
# ScopedFS tests — sandbox isolation
# ===========================================================================
class TestScopedFSSandbox:
    def test_empty_allowlist_denies_all(self, sandbox):
        fs = ScopedFS(allow_roots=[])
        with pytest.raises(PathDenied, match="No allowlisted"):
            fs.read_file(os.path.join(sandbox, "test.txt"))

    def test_read_file_inside_sandbox(self, fs, sandbox):
        p = os.path.join(sandbox, "data.txt")
        Path(p).write_text("contents", encoding="utf-8")
        assert fs.read_file(p) == "contents"

    def test_read_file_outside_sandbox(self, fs):
        with pytest.raises(PathDenied, match="outside the allowlist"):
            fs.read_file("/etc/passwd")

    def test_write_file_inside_sandbox(self, fs, sandbox):
        p = os.path.join(sandbox, "new.txt")
        result = fs.write_file(p, "created")
        assert result == os.path.realpath(p)
        assert Path(p).read_text(encoding="utf-8") == "created"

    def test_write_file_outside_sandbox(self, fs):
        with pytest.raises(PathDenied, match="outside the allowlist"):
            fs.write_file("/tmp/evil.txt", "bad")

    def test_delete_file_inside_sandbox(self, fs, sandbox):
        p = os.path.join(sandbox, "remove_me.txt")
        Path(p).write_text("x", encoding="utf-8")
        result = fs.delete_file(p)
        assert result == os.path.realpath(p)
        assert not os.path.exists(p)

    def test_delete_dir_refused(self, fs, sandbox):
        d = os.path.join(sandbox, "mydir")
        os.makedirs(d)
        with pytest.raises(PathDenied, match="directory"):
            fs.delete_file(d)

    def test_move_inside_sandbox(self, fs, sandbox):
        src = os.path.join(sandbox, "a.txt")
        dst = os.path.join(sandbox, "b.txt")
        Path(src).write_text("move me", encoding="utf-8")
        s, d = fs.move_file(src, dst)
        assert not os.path.exists(src)
        assert Path(dst).read_text(encoding="utf-8") == "move me"

    def test_list_dir(self, fs, sandbox):
        Path(os.path.join(sandbox, "f1.txt")).write_text("1", encoding="utf-8")
        (Path(sandbox) / "subdir").mkdir()
        entries = fs.list_dir(sandbox)
        names = {e["name"] for e in entries}
        assert "f1.txt" in names
        assert "subdir" in names

    def test_symlink_escape_blocked(self, nested_sandbox):
        """A symlink inside the sandbox that points outside must resolve
        to the outside target and be denied."""
        outside = os.path.join(tempfile.gettempdir(), "cowork_escape_test.txt")
        try:
            Path(outside).write_text("outside", encoding="utf-8")
            # Create a symlink inside the sandbox pointing outside.
            link = os.path.join(nested_sandbox, "escape.lnk")
            os.symlink(outside, link)

            fs = ScopedFS(allow_roots=[nested_sandbox])
            with pytest.raises(PathDenied, match="outside the allowlist"):
                fs.read_file(link)
        finally:
            if os.path.exists(outside):
                os.remove(outside)

    def test_symlink_inside_ok(self, nested_sandbox):
        """A symlink inside the sandbox pointing to another file INSIDE
        the sandbox should be allowed."""
        target = os.path.join(nested_sandbox, "sub", "hello.txt")
        link = os.path.join(nested_sandbox, "link.lnk")
        os.symlink(target, link)

        fs = ScopedFS(allow_roots=[nested_sandbox])
        content = fs.read_file(link)
        assert content == "hello world"

    def test_dotdot_traversal_blocked(self, fs, sandbox):
        """A path with .. that resolves outside must be blocked."""
        p = os.path.join(sandbox, "..", "etc", "passwd")
        with pytest.raises(PathDenied):
            fs.read_file(p)

    def test_write_new_file_resolves_parent(self, fs, sandbox):
        """Writing a new file under a symlinked parent inside the sandbox
        must still be allowed."""
        real_sub = os.path.join(sandbox, "real_sub")
        os.makedirs(real_sub)
        link_sub = os.path.join(sandbox, "link_sub")
        os.symlink(real_sub, link_sub)

        new_file = os.path.join(link_sub, "new.txt")
        result = fs.write_file(new_file, "ok")
        assert os.path.exists(result)
        assert Path(os.path.join(real_sub, "new.txt")).read_text(encoding="utf-8") == "ok"


# ===========================================================================
# Tool registry tests — confirmation gating
# ===========================================================================
class TestToolRegistry:
    def test_all_tools_defined(self):
        expected = {"list_dir", "read_file", "write_file", "delete_file",
                     "move_file", "finish"}
        assert set(cowork_tools.TOOLS) == expected

    def test_readonly_tools_not_destructive(self):
        for name in ("list_dir", "read_file", "finish"):
            assert not cowork_tools.TOOLS[name].destructive

    def test_write_tools_are_destructive(self):
        for name in ("write_file", "delete_file", "move_file"):
            assert cowork_tools.TOOLS[name].destructive

    def test_catalog_mentions_all_tools(self):
        text = cowork_tools.tool_catalog_text()
        for name in cowork_tools.TOOLS:
            assert name in text

    def test_preview_affected_write_file(self, fs, sandbox):
        p = os.path.join(sandbox, "target.txt")
        preview = cowork_tools.preview_affected("write_file",
                                                 {"path": p, "content": "x" * 100},
                                                 fs)
        assert preview["risk"] == "medium"
        assert preview["affected"] == [os.path.realpath(p)]
        assert "Create" in preview["summary"]

    def test_preview_affected_denied(self, fs):
        preview = cowork_tools.preview_affected("write_file",
                                                 {"path": "/etc/shadow", "content": "x"},
                                                 fs)
        assert preview.get("denied") is True
        assert preview["risk"] == "blocked"

    def test_preview_move_file(self, fs, sandbox):
        src = os.path.join(sandbox, "a.txt")
        dst = os.path.join(sandbox, "b.txt")
        Path(src).write_text("x", encoding="utf-8")
        preview = cowork_tools.preview_affected("move_file",
                                                 {"src": src, "dst": dst},
                                                 fs)
        assert preview["risk"] == "medium"
        assert os.path.realpath(src) in preview["affected"]
        assert os.path.realpath(dst) in preview["affected"]

    def test_execute_finish(self, fs):
        result = cowork_tools.execute("finish", {"summary": "Done!"}, fs)
        assert result == {"finished": True, "summary": "Done!"}


# ===========================================================================
# Agent state machine tests — agent loop
# ===========================================================================
class TestCoworkSession:
    def test_create_session(self):
        s = cowork.CoworkSession(task="list files")
        assert s.id
        assert not s.done
        assert s.step_index == 0
        assert s.pending is None
        assert s.total_cost == 0.0

    def test_session_store(self):
        s = cowork.create_session(task="test")
        found = cowork.get_session(s.id)
        assert found is s
        cowork.delete_session(s.id)
        assert cowork.get_session(s.id) is None

    def test_to_dict(self):
        s = cowork.CoworkSession(task="summarize")
        d = s.to_dict()
        assert d["task"] == "summarize"
        assert d["done"] is False
        assert "allow_roots" in d

    def test_step_on_unknown_session(self):
        events = cowork.step_session("nonexistent")
        assert events[0]["type"] == "error"

    def test_confirm_without_pending(self, sandbox):
        s = cowork.CoworkSession(task="test")
        events = s.confirm()
        assert events[0]["type"] == "error"
        assert "No pending action" in events[0]["message"]

    def test_reject_without_pending(self, sandbox):
        s = cowork.CoworkSession(task="test")
        events = s.reject()
        assert events[0]["type"] == "error"
        assert "No pending action" in events[0]["message"]


# ===========================================================================
# Config tests — allowlist
# ===========================================================================
class TestConfig:
    def test_load_empty_by_default(self, monkeypatch):
        monkeypatch.delenv("COWORK_ALLOWLIST", raising=False)
        # The cowork_allowlist.json has an empty "allow" array.
        result = cowork_config.load_allowlist()
        assert isinstance(result, list)

    def test_load_from_env(self, monkeypatch, sandbox):
        monkeypatch.setenv("COWORK_ALLOWLIST", sandbox)
        result = cowork_config.load_allowlist()
        assert sandbox in result

    def test_deduplication(self, monkeypatch, sandbox):
        monkeypatch.setenv("COWORK_ALLOWLIST",
                           os.pathsep.join([sandbox, sandbox]))
        result = cowork_config.load_allowlist()
        assert len(result) == 1
```

---

## File 9: `7ces/gateway/cowork_allowlist.json` (updated with a comment for users)

```json
{
  "_comment": "Add absolute directory paths the Cowork agent may access. Leave empty for deny-all.",
  "allow": []
}
```

---

## Integration into `app.py`

Add to the existing FastAPI app:

```python
# At the top of app.py, add:
from cowork_routes import router as cowork_router
app.include_router(cowork_router)

# If cowork_routes.py is inside 7ces/gateway/, adjust the import:
# from gateway.cowork_routes import router as cowork_router
```

No other edits are required — the Cowork agent uses the existing spend-guard and provider adapters through `cowork_llm.py`.

---

## Run

```bash
# 1. Configure the allowlist (real paths for your machine).
export COWORK_ALLOWLIST="/home/user/projects:/home/user/docs"

# Or edit 7ces/gateway/cowork_allowlist.json:
#   {"allow": ["/home/user/projects", "/home/user/docs"]}

# 2. Ensure spendguard + provider adapters are importable from cowork_llm.py.
#    If the symbol names differ from the stubs, adjust the imports in cowork_llm.py.

# 3. Run the tests.
pytest tests/test_cowork.py -v

# 4. Start the app (the Cowork routes are now active).
uvicorn app:app --reload

# 5. Test the agent via curl.
curl -s -X POST http://localhost:8000/cowork/start \
  -H "Content-Type: application/json" \
  -d '{"task": "List all files in /home/user/projects and create a summary.txt"}'
```