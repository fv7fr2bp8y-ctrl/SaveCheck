"""Generate the demo dataset for the web preview from the real pricing core.

Builds a few synthetic 90-day histories, runs them through the actual
verdict/chart logic, and writes ``public/data.js`` so the static site shows
output produced by the same code the app uses — not hand-written mock numbers.

    python scripts/gen_demo_data.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from savecheck.pricing import PricePoint, Verdict, build_chart, evaluate_series  # noqa: E402

REF = date(2026, 6, 13)

BADGE = {
    Verdict.REAL: ("РЕАЛНА ПРОМОЦИЯ", "green"),
    Verdict.COSMETIC: ("ОБИЧАЙНА ЦЕНА", "yellow"),
    Verdict.FAKE: ("ФАЛШИВА ПРОМОЦИЯ", "red"),
    Verdict.UNKNOWN: ("НЯМА ДОСТАТЪЧНО ДАННИ", "gray"),
}


def flat(price: str, day_from: int, day_to: int, promo: bool = False) -> list[PricePoint]:
    return [
        PricePoint.of(REF - timedelta(days=d), price, is_promo=promo)
        for d in range(day_from, day_to - 1, -1)
    ]


def fake_milk() -> tuple[str, str, list[PricePoint]]:
    # 2.49 for months, quietly bumped to 2.99, then "promo" 2.59 today.
    pts = flat("2.49", 90, 15) + flat("2.99", 14, 1) + [PricePoint.of(REF, "2.59", is_promo=True)]
    return "Прясно мляко", "1 л", pts


def real_oil() -> tuple[str, str, list[PricePoint]]:
    pts = flat("3.49", 90, 1) + [PricePoint.of(REF, "2.79", is_promo=True)]
    return "Олио", "1 л", pts


def cosmetic_cheese() -> tuple[str, str, list[PricePoint]]:
    # Typical ~8.50; "promo" today is a trivial 8.30 (~2% off).
    pts = flat("8.50", 90, 1) + [PricePoint.of(REF, "8.30", is_promo=True)]
    return "Кашкавал", "400 г", pts


def unknown_coffee() -> tuple[str, str, list[PricePoint]]:
    # Only a few days of history -> not enough to judge.
    pts = flat("7.99", 4, 1) + [PricePoint.of(REF, "6.99", is_promo=True)]
    return "Кафе", "250 г", pts


def build_entry(name: str, pack: str, pts: list[PricePoint]) -> dict:
    chart = build_chart(pts, REF)
    result = evaluate_series(pts, REF, is_promo=True)
    s = chart.stats
    label, color = BADGE[result.verdict]
    disc = result.discount_vs_median
    return {
        "name": name,
        "package": pack,
        "verdict": color,
        "verdict_label": label,
        "reason": result.reason,
        "discount_pct": round(float(disc) * 100) if disc is not None else None,
        "current_price": float(s.current_price) if s.current_price is not None else None,
        "median_90": float(s.median_90) if s.median_90 is not None else None,
        "min_90": float(s.min_90) if s.min_90 is not None else None,
        "min_30_prior": float(s.min_30_prior) if s.min_30_prior is not None else None,
        "floor_day": chart.floor_day.isoformat() if chart.floor_day else None,
        "series": [
            {"day": p.day.isoformat(), "price": float(p.price), "is_promo": p.is_promo}
            for p in chart.series
        ],
    }


def main() -> None:
    products = [build_entry(*sc()) for sc in (fake_milk, real_oil, cosmetic_cheese, unknown_coffee)]
    payload = {"generated_for": REF.isoformat(), "products": products}
    out = ROOT / "public" / "data.js"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "window.SAVECHECK_DEMO = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {out} ({len(products)} products)")


if __name__ == "__main__":
    main()
