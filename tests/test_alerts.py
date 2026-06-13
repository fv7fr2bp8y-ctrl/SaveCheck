"""Tests for the watchlist / price-alert logic. Pure stdlib; no DB needed."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from savecheck.pricing.aggregates import PricePoint  # noqa: E402
from savecheck.pricing.alerts import WatchRule, evaluate_watch  # noqa: E402
from savecheck.pricing.verdict import evaluate_series  # noqa: E402

REF = date(2026, 6, 13)


def steady(price: str, days: int = 60) -> list[PricePoint]:
    return [PricePoint.of(REF - timedelta(days=d), price) for d in range(1, days + 1)]


def _result(current: str, is_promo: bool):
    return evaluate_series(steady("3.00"), REF, is_promo=is_promo, current_price=Decimal(current))


def test_target_price_triggers_alert():
    res = _result("2.50", is_promo=False)
    decision = evaluate_watch(res, WatchRule(target_price=Decimal("2.60")))
    assert decision.should_notify is True
    assert len(decision.reasons) == 1


def test_target_price_not_reached():
    res = _result("2.80", is_promo=False)
    decision = evaluate_watch(res, WatchRule(target_price=Decimal("2.60")))
    assert decision.should_notify is False


def test_real_promo_triggers_alert():
    res = _result("2.50", is_promo=True)  # ~17% off, near floor -> REAL
    decision = evaluate_watch(res, WatchRule(notify_on_real_promo=True))
    assert decision.should_notify is True


def test_fake_promo_does_not_trigger_real_promo_alert():
    res = _result("3.00", is_promo=True)  # FAKE
    decision = evaluate_watch(res, WatchRule(notify_on_real_promo=True))
    assert decision.should_notify is False


def test_both_rules_can_fire_together():
    res = _result("2.50", is_promo=True)
    decision = evaluate_watch(
        res, WatchRule(target_price=Decimal("2.60"), notify_on_real_promo=True)
    )
    assert decision.should_notify is True
    assert len(decision.reasons) == 2


def test_empty_rule_never_fires():
    res = _result("2.50", is_promo=True)
    decision = evaluate_watch(res, WatchRule())
    assert decision.should_notify is False


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{('OK' if not failures else str(failures) + ' FAILED')}")
    sys.exit(1 if failures else 0)
