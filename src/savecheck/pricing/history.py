"""Build the 90-day price chart series for the UI.

Pure stdlib. Turns sparse observations into a continuous daily series (prices
persist until changed, so gaps are carried forward) and annotates it with the
markers the app shows: the typical-price (median) line and the true 90-day low.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .aggregates import WINDOW_DAYS, PricePoint, PriceStats, compute_stats


@dataclass(frozen=True)
class HistoryPoint:
    day: date
    price: Decimal
    is_promo: bool


@dataclass(frozen=True)
class HistoryChart:
    series: list[HistoryPoint]  # one point per day, oldest -> newest
    stats: PriceStats  # median_90 / min_90 / etc. for the marker lines
    floor_day: date | None  # most recent day the 90-day low was seen


def _by_day(points: list[PricePoint]) -> dict[date, PricePoint]:
    """Collapse multiple observations on one day to the lowest (paid) price."""
    chosen: dict[date, PricePoint] = {}
    for p in points:
        cur = chosen.get(p.day)
        if cur is None or p.price < cur.price:
            chosen[p.day] = p
    return chosen


def build_chart(
    points: list[PricePoint],
    reference_day: date,
    window_days: int = WINDOW_DAYS,
    carry_forward: bool = True,
) -> HistoryChart:
    """Build a continuous daily chart for ``[reference_day - window, reference_day]``.

    Leading days before the first observation are omitted (we don't invent
    history). Interior gaps are filled by carrying the last known price forward
    when ``carry_forward`` is set.
    """
    window_start = reference_day - timedelta(days=window_days)
    by_day = _by_day([p for p in points if window_start <= p.day <= reference_day])

    series: list[HistoryPoint] = []
    last: PricePoint | None = None
    day = window_start
    while day <= reference_day:
        obs = by_day.get(day)
        if obs is not None:
            last = obs
            series.append(HistoryPoint(day=day, price=obs.price, is_promo=obs.is_promo))
        elif last is not None and carry_forward:
            # Carry the last known price; it is no longer a promo day by default.
            series.append(HistoryPoint(day=day, price=last.price, is_promo=False))
        day += timedelta(days=1)

    stats = compute_stats(points, reference_day)
    floor_day = _floor_day(by_day, stats.min_90)
    return HistoryChart(series=series, stats=stats, floor_day=floor_day)


def _floor_day(by_day: dict[date, PricePoint], min_90: Decimal | None) -> date | None:
    """Most recent day we actually *observed* the 90-day low.

    Uses real observations (not carry-forward fill) so the marker points at a
    day the price was genuinely this cheap — "last time it was this low".
    """
    if min_90 is None:
        return None
    days = [day for day, p in by_day.items() if p.price == min_90]
    return max(days) if days else None
