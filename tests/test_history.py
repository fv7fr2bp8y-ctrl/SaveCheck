"""Tests for the 90-day chart builder. Pure stdlib; no DB needed."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from savecheck.pricing.aggregates import PricePoint  # noqa: E402
from savecheck.pricing.history import build_chart  # noqa: E402

REF = date(2026, 6, 13)


def test_series_is_continuous_and_carries_forward():
    # Two observations 3 days apart; gap days inherit the earlier price.
    points = [PricePoint.of(REF - timedelta(days=3), "3.00"), PricePoint.of(REF, "2.50")]
    chart = build_chart(points, REF, window_days=5)
    # Days: ref-3, ref-2, ref-1, ref  -> nothing before first observation.
    assert [p.day for p in chart.series] == [
        REF - timedelta(days=3),
        REF - timedelta(days=2),
        REF - timedelta(days=1),
        REF,
    ]
    assert chart.series[1].price == Decimal("3.00")  # carried forward
    assert chart.series[-1].price == Decimal("2.50")


def test_no_invented_history_before_first_observation():
    points = [PricePoint.of(REF, "2.00")]
    chart = build_chart(points, REF, window_days=10)
    assert len(chart.series) == 1
    assert chart.series[0].day == REF


def test_carry_forward_can_be_disabled():
    points = [PricePoint.of(REF - timedelta(days=2), "3.00"), PricePoint.of(REF, "2.50")]
    chart = build_chart(points, REF, window_days=5, carry_forward=False)
    assert [p.day for p in chart.series] == [REF - timedelta(days=2), REF]


def test_floor_day_is_most_recent_low():
    points = [
        PricePoint.of(REF - timedelta(days=10), "2.00"),
        PricePoint.of(REF - timedelta(days=5), "3.00"),
        PricePoint.of(REF - timedelta(days=2), "2.00"),
    ]
    chart = build_chart(points, REF)
    assert chart.stats.min_90 == Decimal("2.00")
    # Both day-10 and day-2 hit 2.00 (carry-forward keeps 2.00 through to day-2);
    # the floor marker points at the most recent low.
    assert chart.floor_day == REF - timedelta(days=2)


def test_lowest_price_wins_on_a_day_with_multiple_observations():
    points = [PricePoint.of(REF, "3.00"), PricePoint.of(REF, "2.40", is_promo=True)]
    chart = build_chart(points, REF, window_days=3)
    assert chart.series[-1].price == Decimal("2.40")
    assert chart.series[-1].is_promo is True


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
