"""
Loop engineering — Discovery + Persistence (Paper 1, moves 1 & 4).

Discovery: scan the vault for actionable TODO items that need estimation.
Persistence: checkpoint loop state to disk so it survives gateway restarts.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Vault location
VAULT_ROOT = Path(os.environ.get("7CES_VAULT", os.path.expanduser("~/7CEs-Vault")))

# Loop state file (survives gateway restart)
LOOP_STATE_PATH = Path(__file__).resolve().parent / "loop_state.json"


def _find_vault() -> Path | None:
    """Locate the vault on this machine."""
    candidates = [
        VAULT_ROOT,
        Path("C:/Users/adam1/7CEs-Vault"),
        Path(os.path.expanduser("~/7CEs-Vault")),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def discover_tasks() -> list[dict[str, Any]]:
    """Scan vault for actionable TODO items. Returns list of {file, line, text, priority}."""
    vault = _find_vault()
    if not vault:
        return []

    tasks = []
    todo_pattern = re.compile(r"-\s*\[ \]\s+(.+)", re.IGNORECASE)

    # Check Active Priorities
    ap = vault / "Active Priorities.md"
    if ap.exists():
        for i, line in enumerate(ap.read_text(encoding="utf-8").splitlines(), 1):
            m = todo_pattern.match(line.strip())
            if m:
                tasks.append({
                    "file": "Active Priorities.md",
                    "line": i,
                    "text": m.group(1).strip(),
                    "priority": "high" if i < 10 else "medium",
                    "source": "vault",
                })

    # Check project folders
    projects_dir = vault / "02 - Projects"
    if projects_dir.exists():
        for md in projects_dir.rglob("*.md"):
            for i, line in enumerate(md.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                m = todo_pattern.match(line.strip())
                if m:
                    tasks.append({
                        "file": str(md.relative_to(vault)),
                        "line": i,
                        "text": m.group(1).strip(),
                        "priority": "medium",
                        "source": "project",
                    })

    return tasks


def load_state() -> dict[str, Any]:
    """Load persisted loop state."""
    if LOOP_STATE_PATH.exists():
        try:
            return json.loads(LOOP_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_scan": None, "tasks_found": 0, "estimates_generated": 0, "sessions": []}


def save_state(state: dict[str, Any]) -> None:
    """Persist loop state to disk."""
    state["last_scan"] = datetime.now(timezone.utc).isoformat()
    LOOP_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def pending_manifest() -> dict[str, Any]:
    """Generate a pending-work manifest for the /tasks/pending endpoint."""
    tasks = discover_tasks()
    state = load_state()

    # Tag tasks that need estimation (don't have estimates yet)
    for t in tasks:
        t["needs_estimation"] = True  # In future: check if estimate exists in ledger

    return {
        "tasks": tasks,
        "count": len(tasks),
        "state": state,
        "vault": str(_find_vault()) if _find_vault() else None,
    }
