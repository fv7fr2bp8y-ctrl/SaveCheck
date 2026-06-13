"""Tests for the rolling-statistics computation. Pure stdlib; no DB needed."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from savecheck.pricing.aggregates import PricePoint, compute_stats  # noqa: E402

REF = date(2026, 6, 13)


def _series(prices_by_offset: dict[int, str]) -> list[PricePoint]:
    """Build points where the key is 'days before REF'."""
    return [PricePoint.of(REF - timedelta(days=off), p) for off, p in prices_by_offset.items()]


def test_empty_series_yields_no_stats():
    stats = compute_stats([], REF)
    assert stats.sample_size_90 == 0
    assert stats.median_90 is None
    assert stats.min_90 is None
    assert stats.current_price is None
    assert not stats.has_history


def test_basic_window_aggregates():
    points = _series({1: "2.00", 10: "3.00", 20: "4.00"})
    stats = compute_stats(points, REF)
    assert stats.min_90 == Decimal("2.00")
    assert stats.max_90 == Decimal("4.00")
    assert stats.median_90 == Decimal("3.00")
    assert stats.sample_size_90 == 3


def test_observations_older_than_90_days_are_excluded():
    points = _series({1: "5.00", 95: "1.00"})  # the 1.00 is 95 days old
    stats = compute_stats(points, REF)
    assert stats.sample_size_90 == 1
    assert stats.min_90 == Decimal("5.00")


def test_current_price_resolves_to_latest_day():
    points = _series({0: "2.50", 5: "3.00"})
    stats = compute_stats(points, REF)
    assert stats.current_price == Decimal("2.50")


def test_current_price_prefers_lowest_on_latest_day():
    # Two observations on the same (latest) day: shopper pays the lower one.
    points = [PricePoint.of(REF, "3.00"), PricePoint.of(REF, "2.40", is_promo=True)]
    stats = compute_stats(points, REF)
    assert stats.current_price == Decimal("2.40")


def test_explicit_current_price_overrides():
    points = _series({0: "3.00"})
    stats = compute_stats(points, REF, current_price=Decimal("1.99"))
    assert stats.current_price == Decimal("1.99")


def test_min_30_prior_excludes_reference_day_itself():
    # A cheap price ON the reference day must not count as the "prior" low.
    points = _series({0: "1.00", 5: "3.00", 15: "2.80"})
    stats = compute_stats(points, REF)
    assert stats.min_30_prior == Decimal("2.80")


def test_min_30_prior_window_boundary():
    points = _series({10: "2.00", 31: "1.00"})  # 31 days old is outside the 30d prior
    stats = compute_stats(points, REF)
    assert stats.min_30_prior == Decimal("2.00")


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
