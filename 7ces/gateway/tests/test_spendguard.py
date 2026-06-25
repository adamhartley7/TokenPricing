"""Spend guard — the pre-call cap decisions."""
from config import config
from ledger import fresh_test_ledger
from spendguard import SpendGuard


def _guard():
    return SpendGuard(fresh_test_ledger()), config


def test_within_caps_allows():
    guard, _ = _guard()
    d = guard.check(
        provider="deepseek", model="deepseek-v4-flash",
        input_tokens=500, max_output_tokens=200, session_id="s1",
    )
    assert d.allowed
    assert d.worst_case_usd < 0.01


def test_per_request_cap_denies():
    guard, _ = _guard()
    # Huge input on Opus blows past the $0.50 per-request cap.
    d = guard.check(
        provider="anthropic", model="claude-opus-4-8",
        input_tokens=1_000_000, max_output_tokens=1000, session_id="s1",
    )
    assert not d.allowed
    assert "per-request cap" in d.reason


def test_per_request_cap_override_header():
    guard, _ = _guard()
    # A tiny override cap denies an otherwise-cheap call.
    d = guard.check(
        provider="deepseek", model="deepseek-v4-flash",
        input_tokens=500, max_output_tokens=2000, session_id="s1",
        per_request_cap_override=0.00000001,
    )
    assert not d.allowed


def test_session_cap_denies(monkeypatch):
    led = fresh_test_ledger()
    guard = SpendGuard(led)
    monkeypatch.setattr(config, "cap_per_session", 0.001)
    # Pre-spend most of the session budget.
    led.record(session_id="s1", provider="deepseek", model="deepseek-v4-flash", cost_usd=0.0009)
    d = guard.check(
        provider="deepseek", model="deepseek-v4-flash",
        input_tokens=2000, max_output_tokens=2000, session_id="s1",
    )
    assert not d.allowed
    assert "per-session cap" in d.reason


def test_day_cap_denies(monkeypatch):
    led = fresh_test_ledger()
    guard = SpendGuard(led)
    monkeypatch.setattr(config, "cap_per_day", 0.001)
    led.record(session_id="other", provider="deepseek", model="deepseek-v4-flash", cost_usd=0.00095)
    d = guard.check(
        provider="deepseek", model="deepseek-v4-flash",
        input_tokens=2000, max_output_tokens=2000, session_id="s2",
    )
    assert not d.allowed
    assert "per-day cap" in d.reason


def test_unknown_model_fails_closed():
    guard, _ = _guard()
    d = guard.check(
        provider="deepseek", model="totally-unknown-model",
        input_tokens=10, max_output_tokens=10, session_id="s1",
    )
    assert not d.allowed
    assert d.worst_case_usd == float("inf")


def test_capped_entries_do_not_count_as_spend():
    led = fresh_test_ledger()
    led.record(session_id="s1", provider="deepseek", model="deepseek-v4-flash",
               cost_usd=0.0, capped=True, note="refused")
    assert led.session_total("s1") == 0.0


def test_reservation_prevents_concurrent_overshoot(monkeypatch):
    # Two in-flight calls must not collectively exceed the session cap (TOCTOU). The first call's
    # hold makes the second see the reduced budget and be denied — until the first releases.
    led = fresh_test_ledger()
    guard = SpendGuard(led)
    monkeypatch.setattr(config, "cap_per_session", 0.01)
    kw = dict(provider="deepseek", model="deepseek-v4-pro",
              input_tokens=5000, max_output_tokens=5000, session_id="s1")

    d1 = guard.check(**kw)
    assert d1.allowed                       # ~$0.0072 reserved
    d2 = guard.check(**kw)
    assert not d2.allowed                    # second hold would push past $0.01
    assert "per-session cap" in d2.reason

    guard.release("s1", d1.worst_case_usd)   # first call settled
    d3 = guard.check(**kw)
    assert d3.allowed                        # budget freed up again


def test_release_is_safe_to_overshoot():
    guard = SpendGuard(fresh_test_ledger())
    guard.release("nobody", 1.0)  # releasing a non-existent hold must not error or go negative
    assert guard._pending_session("nobody") == 0.0
