"""
Cost ledger — a small SQLite store recording the ACTUAL cost of every call, plus any pre-call
refusals. Powers the running cost meter (per request / per session / per provider / per day).

Definitions:
  * request  = one row.
  * session  = the gateway process lifetime (a session id is generated at startup). A client may
               override it with the `x-7Cs-session` header to group its own runs.
  * day      = calendar day in UTC.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from config import config

# One session id per gateway process (overridable per-request via header).
SESSION_ID = uuid.uuid4().hex[:12]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    iso           TEXT    NOT NULL,
    session_id    TEXT    NOT NULL,
    provider      TEXT    NOT NULL,
    model         TEXT    NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL    NOT NULL DEFAULT 0,
    capped        INTEGER NOT NULL DEFAULT 0,   -- 1 = refused before the call (no spend)
    note          TEXT    NOT NULL DEFAULT '',
    -- TOP protocol schema delta (all nullable, backward-compatible)
    task_class    TEXT,
    profile_json  TEXT,
    estimate_method TEXT,
    estimate_p10  INTEGER,
    estimate_p50  INTEGER,
    estimate_p90  INTEGER,
    est_cost_p50  REAL,
    turns         INTEGER,
    cache_read_tokens  INTEGER,
    cache_creation_tokens INTEGER
);
CREATE INDEX IF NOT EXISTS idx_entries_session ON entries(session_id);
CREATE INDEX IF NOT EXISTS idx_entries_ts ON entries(ts);
CREATE INDEX IF NOT EXISTS idx_entries_task_class ON entries(task_class);
"""


def _ensure_columns(conn: sqlite3.Connection):
    """Idempotent migration: add TOP columns if they don't exist yet."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
    new_cols = [
        ("task_class", "TEXT"),
        ("profile_json", "TEXT"),
        ("estimate_method", "TEXT"),
        ("estimate_p10", "INTEGER"),
        ("estimate_p50", "INTEGER"),
        ("estimate_p90", "INTEGER"),
        ("est_cost_p50", "REAL"),
        ("turns", "INTEGER"),
        ("cache_read_tokens", "INTEGER"),
        ("cache_creation_tokens", "INTEGER"),
    ]
    for name, typ in new_cols:
        if name not in cols:
            conn.execute(f"ALTER TABLE entries ADD COLUMN {name} {typ}")


def _start_of_today_utc() -> float:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


class Ledger:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or config.ledger_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            _ensure_columns(self._conn)
            self._conn.commit()

    # -- writes ---------------------------------------------------------------
    def record(
        self,
        *,
        session_id: str,
        provider: str,
        model: str,
        cost_usd: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        capped: bool = False,
        note: str = "",
        # TOP protocol schema delta (all nullable/defaulted, backward-compatible)
        task_class: str | None = None,
        profile_json: str | None = None,
        estimate_method: str | None = None,
        estimate_p10: int | None = None,
        estimate_p50: int | None = None,
        estimate_p90: int | None = None,
        est_cost_p50: float | None = None,
        turns: int | None = None,
        cache_read_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._conn.execute(
                "INSERT INTO entries (ts, iso, session_id, provider, model, input_tokens, "
                "output_tokens, cost_usd, capped, note, task_class, profile_json, "
                "estimate_method, estimate_p10, estimate_p50, estimate_p90, est_cost_p50, "
                "turns, cache_read_tokens, cache_creation_tokens) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    now.timestamp(), now.isoformat(), session_id, provider, model,
                    int(input_tokens), int(output_tokens), float(cost_usd),
                    1 if capped else 0, note,
                    task_class, profile_json, estimate_method,
                    estimate_p10, estimate_p50, estimate_p90, est_cost_p50,
                    turns, cache_read_tokens, cache_creation_tokens,
                ),
            )
            self._conn.commit()

    def class_samples(self, task_class: str, limit: int = 200) -> list[dict]:
        """Return rows for a given task class (for calibration)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM entries WHERE task_class=? AND capped=0 "
                "ORDER BY id DESC LIMIT ?",
                (task_class, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- reads (only non-capped rows count as spend) --------------------------
    def session_total(self, session_id: str) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd),0) AS t FROM entries WHERE session_id=? AND capped=0",
                (session_id,),
            ).fetchone()
        return float(row["t"])

    def day_total(self) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd),0) AS t FROM entries WHERE ts>=? AND capped=0",
                (_start_of_today_utc(),),
            ).fetchone()
        return float(row["t"])

    def provider_totals(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT provider, COALESCE(SUM(cost_usd),0) AS t, COUNT(*) AS n "
                "FROM entries WHERE capped=0 GROUP BY provider"
            ).fetchall()
        return {r["provider"]: {"cost_usd": float(r["t"]), "calls": int(r["n"])} for r in rows}

    def recent(self, n: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT iso, session_id, provider, model, input_tokens, output_tokens, "
                "cost_usd, capped, note FROM entries ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [dict(r) for r in rows]

    def meter_snapshot(self, session_id: str = SESSION_ID) -> dict:
        return {
            "session_id": session_id,
            "caps": config.caps(),
            "totals": {
                "session_usd": round(self.session_total(session_id), 6),
                "today_usd": round(self.day_total(), 6),
            },
            "by_provider": self.provider_totals(),
            "recent": self.recent(20),
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def fresh_test_ledger() -> Ledger:
    """An isolated in-memory ledger for tests."""
    led = Ledger.__new__(Ledger)
    led.path = ":memory:"
    led._lock = threading.Lock()
    led._conn = sqlite3.connect(":memory:", check_same_thread=False)
    led._conn.row_factory = sqlite3.Row
    led._conn.executescript(_SCHEMA)
    led._conn.commit()
    return led
