"""The promotion "traffic light" verdict.

Given the rolling statistics for a product, decide whether a price is a real
deal (green), an unremarkable / cosmetic one (yellow), or a misleading "fake"
promotion (red). The fake-promo test follows the spirit of the EU Omnibus
directive: a discount must be measured against the lowest price applied in the
30 days *before* the promotion, not against an inflated "old price" on the tag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from .aggregates import PricePoint, PriceStats, compute_stats


class Verdict(str, Enum):
    """User-facing traffic-light states."""

    REAL = "green"  # genuinely cheap right now
    COSMETIC = "yellow"  # ordinary price or a trivial discount
    FAKE = "red"  # advertised as a promo but you are not actually saving
    UNKNOWN = "gray"  # not enough price history to judge


@dataclass(frozen=True)
class VerdictConfig:
    """Tunable thresholds. Defaults are sensible starting points, not gospel."""

    min_sample_90: int = 10  # need at least this many observations to judge
    real_discount: Decimal = Decimal("0.07")  # >=7% below the 90-day median
    cosmetic_discount: Decimal = Decimal("0.02")  # >=2% counts as a small real cut
    near_floor_pct: Decimal = Decimal("0.05")  # within 5% of the 90-day low


@dataclass(frozen=True)
class VerdictResult:
    verdict: Verdict
    reason: str  # short, user-facing (Bulgarian) explanation
    discount_vs_median: Decimal | None  # fraction, e.g. Decimal("0.12") == 12%
    stats: PriceStats


def evaluate(
    stats: PriceStats,
    is_promo: bool,
    cfg: VerdictConfig | None = None,
) -> VerdictResult:
    """Turn rolling stats + a promo flag into a verdict.

    ``is_promo`` is whether the item is currently advertised as a promotion
    (e.g. has a struck-through old price). It is what separates a misleading
    "fake" promo from a simply unremarkable everyday price.
    """
    cfg = cfg or VerdictConfig()

    # Cold start: not enough history to say anything trustworthy.
    if (
        stats.current_price is None
        or stats.median_90 is None
        or stats.min_90 is None
        or stats.median_90 <= 0
        or stats.sample_size_90 < cfg.min_sample_90
    ):
        return VerdictResult(
            verdict=Verdict.UNKNOWN,
            reason="Няма достатъчно история на цената, за да преценим.",
            discount_vs_median=None,
            stats=stats,
        )

    current = stats.current_price
    discount = (stats.median_90 - current) / stats.median_90
    near_floor = current <= stats.min_90 * (Decimal(1) + cfg.near_floor_pct)
    # Omnibus: a genuine discount must beat the lowest price of the prior 30 days.
    cheaper_than_prior = stats.min_30_prior is None or current < stats.min_30_prior

    pct = (discount * 100).quantize(Decimal("1"))

    # Headline anti-fake-promo case: marketed as a deal, but you pay the same as
    # (or more than) the recent 30-day low.
    if is_promo and not cheaper_than_prior:
        return VerdictResult(
            verdict=Verdict.FAKE,
            reason="Фалшива промоция: не е по-евтино от обичайното за последните 30 дни.",
            discount_vs_median=discount,
            stats=stats,
        )

    if discount >= cfg.real_discount and near_floor and cheaper_than_prior:
        return VerdictResult(
            verdict=Verdict.REAL,
            reason=f"Реално намаление: {pct}% под обичайната цена, близо до 90-дневното дъно.",
            discount_vs_median=discount,
            stats=stats,
        )

    if discount >= cfg.cosmetic_discount:
        return VerdictResult(
            verdict=Verdict.COSMETIC,
            reason=f"Малка реална отстъпка: {pct}% под обичайната цена.",
            discount_vs_median=discount,
            stats=stats,
        )

    # No meaningful discount. If it is being sold as a promo, that is misleading.
    if is_promo:
        return VerdictResult(
            verdict=Verdict.FAKE,
            reason="Фалшива промоция: цената е на нивото на обичайната.",
            discount_vs_median=discount,
            stats=stats,
        )

    return VerdictResult(
        verdict=Verdict.COSMETIC,
        reason="Обичайна цена — нищо особено в момента.",
        discount_vs_median=discount,
        stats=stats,
    )


def evaluate_series(
    points: list[PricePoint],
    reference_day: date,
    is_promo: bool,
    current_price: Decimal | None = None,
    cfg: VerdictConfig | None = None,
) -> VerdictResult:
    """Convenience wrapper: compute stats from raw points, then evaluate."""
    stats = compute_stats(points, reference_day, current_price=current_price)
    return evaluate(stats, is_promo=is_promo, cfg=cfg)
