"""Rolling price statistics for a single product at a single chain.

All money is represented with :class:`decimal.Decimal` to avoid float rounding
errors on prices. The functions here are pure: given a list of observations and
a reference day, they return the statistics SaveCheck needs to judge a promo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

# Window lengths, in days.
WINDOW_DAYS = 90  # the "typical price" history window
PRIOR_DAYS = 30  # Omnibus reference window: the 30 days *before* the promo


@dataclass(frozen=True)
class PricePoint:
    """A single observed shelf price on a given day."""

    day: date
    price: Decimal
    is_promo: bool = False

    @classmethod
    def of(cls, day: date, price: str | int | float | Decimal, is_promo: bool = False) -> "PricePoint":
        """Convenience constructor that coerces ``price`` to ``Decimal`` safely.

        Strings and ints/floats are routed through ``str`` first so that e.g.
        ``0.1`` becomes ``Decimal("0.1")`` rather than the binary-float noise.
        """
        return cls(day=day, price=Decimal(str(price)), is_promo=is_promo)


@dataclass(frozen=True)
class PriceStats:
    """Derived statistics relative to a reference day.

    Fields are ``None`` when there is no data to compute them, so callers must
    handle the cold-start / missing-data case explicitly.
    """

    reference_day: date
    current_price: Decimal | None
    median_90: Decimal | None
    min_90: Decimal | None
    max_90: Decimal | None
    min_30_prior: Decimal | None  # lowest price in [ref-30, ref-1], the legal reference
    sample_size_90: int

    @property
    def has_history(self) -> bool:
        return self.sample_size_90 > 0


def _resolve_current(points: list[PricePoint], reference_day: date) -> Decimal | None:
    """Pick the price in effect on ``reference_day`` (latest day <= reference)."""
    on_or_before = [p for p in points if p.day <= reference_day]
    if not on_or_before:
        return None
    latest_day = max(p.day for p in on_or_before)
    # If multiple observations share the latest day, prefer the lowest (the
    # promo price a shopper would actually pay).
    return min(p.price for p in on_or_before if p.day == latest_day)


def compute_stats(
    points: list[PricePoint],
    reference_day: date,
    current_price: Decimal | None = None,
) -> PriceStats:
    """Compute rolling statistics for a product/chain as of ``reference_day``.

    ``current_price`` lets the caller override the price under evaluation (for
    example the promo price printed on the shelf tag being scanned). When
    omitted, the price in effect on ``reference_day`` is used.
    """
    window_start = reference_day - timedelta(days=WINDOW_DAYS)
    prior_start = reference_day - timedelta(days=PRIOR_DAYS)

    window = [p.price for p in points if window_start <= p.day <= reference_day]
    prior = [p.price for p in points if prior_start <= p.day <= reference_day - timedelta(days=1)]

    if current_price is None:
        current_price = _resolve_current(points, reference_day)

    return PriceStats(
        reference_day=reference_day,
        current_price=current_price,
        median_90=median(window) if window else None,
        min_90=min(window) if window else None,
        max_90=max(window) if window else None,
        min_30_prior=min(prior) if prior else None,
        sample_size_90=len(window),
    )
