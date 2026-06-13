"""Price-alert (watchlist) logic.

Pure stdlib and decoupled from persistence: the decision works on plain values
(a target price + flags) plus a computed :class:`VerdictResult`, so it is fully
unit-testable. The DB-backed ``Watch`` model lives in ``models.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .verdict import Verdict, VerdictResult


@dataclass(frozen=True)
class WatchRule:
    """What a user wants to be notified about for one product."""

    target_price: Decimal | None = None  # fire when current price <= target
    notify_on_real_promo: bool = False  # fire when the verdict turns REAL (🟢)


@dataclass(frozen=True)
class AlertDecision:
    should_notify: bool
    reasons: tuple[str, ...]  # user-facing (Bulgarian) reasons, possibly several


def evaluate_watch(result: VerdictResult, rule: WatchRule) -> AlertDecision:
    """Decide whether a watch should fire, given the current verdict/stats."""
    current = result.stats.current_price
    reasons: list[str] = []

    if (
        rule.target_price is not None
        and current is not None
        and current <= rule.target_price
    ):
        reasons.append(f"Цената падна до {current} лв (целта ти беше {rule.target_price} лв).")

    if rule.notify_on_real_promo and result.verdict is Verdict.REAL:
        reasons.append(f"Реална промоция: {result.reason}")

    return AlertDecision(should_notify=bool(reasons), reasons=tuple(reasons))
