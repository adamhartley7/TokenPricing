"""
The spend guard — the brief's #1 non-negotiable. Given a pre-flight input-token estimate and the
request's max_tokens, it computes a worst-case USD cost and decides whether the call may proceed,
BEFORE anything is forwarded to a paid API.

Three caps, all enforced together (USD):
  * per-request : worst-case cost of THIS call
  * per-session : running session spend + this call's worst case
  * per-day     : running day spend + this call's worst case

Fail closed: if a model can't be priced, the call is denied (never forwarded "to be safe").
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import pricing
from config import config
from ledger import Ledger


@dataclass
class Decision:
    allowed: bool
    reason: str
    worst_case_usd: float
    per_request_cap: float
    input_tokens: int
    max_output_tokens: int
    session_total_usd: float
    day_total_usd: float
    model: str
    detail: dict = field(default_factory=dict)

    def as_error_payload(self) -> dict:
        """Structured 402 body returned to the client when a call is refused."""
        return {
            "error": {
                "type": "spend_cap_exceeded",
                "message": self.reason,
                "worst_case_usd": round(self.worst_case_usd, 6),
                "caps": {
                    "per_request_usd": self.per_request_cap,
                    "per_session_usd": config.cap_per_session,
                    "per_day_usd": config.cap_per_day,
                },
                "running": {
                    "session_usd": round(self.session_total_usd, 6),
                    "day_usd": round(self.day_total_usd, 6),
                },
                "estimate": {
                    "input_tokens": self.input_tokens,
                    "max_output_tokens": self.max_output_tokens,
                    "model": self.model,
                },
            }
        }


class SpendGuard:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
        # In-flight reservations (worst-case holds) per session, protected by a lock so that
        # check-and-reserve is ATOMIC. Without this, concurrent requests read the same pre-call
        # totals and could collectively overshoot the session/day caps (a TOCTOU race). A hold is
        # placed when a call is allowed and released() once the call finishes (success or failure).
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()

    def _pending_session(self, session_id: str) -> float:
        return self._pending.get(session_id, 0.0)

    def _pending_all(self) -> float:
        return sum(self._pending.values())

    def release(self, session_id: str, amount: float) -> None:
        """Release a worst-case hold once the call has settled. Must be called for every allow."""
        with self._lock:
            remaining = self._pending.get(session_id, 0.0) - amount
            if remaining > 1e-12:
                self._pending[session_id] = remaining
            else:
                self._pending.pop(session_id, None)

    def check(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        max_output_tokens: int,
        session_id: str,
        per_request_cap_override: float | None = None,
    ) -> Decision:
        per_request_cap = (
            per_request_cap_override
            if per_request_cap_override is not None
            else config.cap_per_request
        )

        # Price the worst case; if the model is unknown we cannot bound cost -> deny (fail-closed).
        try:
            base = pricing.worst_case_usd(model, input_tokens, max_output_tokens)
        except pricing.PricingError as exc:
            return Decision(
                allowed=False,
                reason=f"Refused: {exc}. Cannot bound cost, so the call is blocked (fail-closed).",
                worst_case_usd=float("inf"),
                per_request_cap=per_request_cap,
                input_tokens=input_tokens,
                max_output_tokens=max_output_tokens,
                session_total_usd=0.0,
                day_total_usd=0.0,
                model=model,
            )

        worst = base * config.estimate_safety_factor

        # Atomic: read committed (ledger) + in-flight (pending) totals, decide, and reserve.
        with self._lock:
            session_total = self.ledger.session_total(session_id) + self._pending_session(session_id)
            day_total = self.ledger.day_total() + self._pending_all()

            def deny(reason: str) -> Decision:
                return Decision(
                    allowed=False, reason=reason, worst_case_usd=worst,
                    per_request_cap=per_request_cap, input_tokens=input_tokens,
                    max_output_tokens=max_output_tokens, session_total_usd=session_total,
                    day_total_usd=day_total, model=model,
                )

            if worst > per_request_cap:
                return deny(
                    f"Refused: this request could cost up to ${worst:.4f}, over the per-request cap "
                    f"of ${per_request_cap:.4f}. Lower max_tokens, choose a cheaper model, or raise the cap."
                )
            if session_total + worst > config.cap_per_session:
                return deny(
                    f"Refused: session spend ${session_total:.4f} + up to ${worst:.4f} would exceed the "
                    f"per-session cap of ${config.cap_per_session:.4f}."
                )
            if day_total + worst > config.cap_per_day:
                return deny(
                    f"Refused: today's spend ${day_total:.4f} + up to ${worst:.4f} would exceed the "
                    f"per-day cap of ${config.cap_per_day:.4f}."
                )

            # Allowed — reserve the worst-case hold before releasing the lock.
            self._pending[session_id] = self._pending_session(session_id) + worst

        return Decision(
            allowed=True,
            reason="within caps",
            worst_case_usd=worst,
            per_request_cap=per_request_cap,
            input_tokens=input_tokens,
            max_output_tokens=max_output_tokens,
            session_total_usd=session_total,
            day_total_usd=day_total,
            model=model,
        )
