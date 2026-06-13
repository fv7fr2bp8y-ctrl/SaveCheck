"""Generate the demo dataset for the web preview from the real pricing core.

Builds a few synthetic 90-day histories, runs them through the actual
verdict/chart logic, and writes ``public/data.js``. The output is currency- and
language-neutral (prices are the BGN base); the website applies FX conversion,
currency formatting and translations per selected country. Product names and UI
strings live in the site (i18n), keyed by the stable product ``id`` here.

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
from savecheck.shopping import (  # noqa: E402
    Staple,
    build_shopping_list,
    merge_inventory,
    to_inventory_item,
)

REF = date(2026, 6, 13)


def flat(price: str, day_from: int, day_to: int, promo: bool = False) -> list[PricePoint]:
    return [
        PricePoint.of(REF - timedelta(days=d), price, is_promo=promo)
        for d in range(day_from, day_to - 1, -1)
    ]


# (id, unit kind, base size in that unit, points)
def fake_milk():
    pts = flat("2.49", 90, 15) + flat("2.99", 14, 1) + [PricePoint.of(REF, "2.59", is_promo=True)]
    return "milk", "l", Decimal("1"), pts


def real_oil():
    pts = flat("3.49", 90, 1) + [PricePoint.of(REF, "2.79", is_promo=True)]
    return "oil", "l", Decimal("1"), pts


def cosmetic_cheese():
    pts = flat("8.50", 90, 1) + [PricePoint.of(REF, "8.30", is_promo=True)]
    return "cheese", "kg", Decimal("0.4"), pts


def unknown_coffee():
    pts = flat("7.99", 4, 1) + [PricePoint.of(REF, "6.99", is_promo=True)]
    return "coffee", "kg", Decimal("0.25"), pts


def real_flour():
    pts = flat("1.59", 90, 1) + [PricePoint.of(REF, "1.29", is_promo=True)]
    return "flour", "kg", Decimal("1"), pts


def fake_sugar():
    pts = flat("2.19", 90, 15) + flat("2.59", 14, 1) + [PricePoint.of(REF, "2.29", is_promo=True)]
    return "sugar", "kg", Decimal("1"), pts


def cosmetic_bread():
    pts = flat("1.49", 90, 1) + [PricePoint.of(REF, "1.45", is_promo=True)]
    return "bread", "kg", Decimal("0.7"), pts


def cosmetic_rice():
    pts = flat("2.99", 90, 1) + [PricePoint.of(REF, "2.92", is_promo=True)]
    return "rice", "kg", Decimal("1"), pts


def real_tomatoes():
    pts = flat("3.49", 90, 1) + [PricePoint.of(REF, "2.49", is_promo=True)]
    return "tomatoes", "kg", Decimal("1"), pts


def real_oliveoil():
    pts = flat("12.99", 90, 1) + [PricePoint.of(REF, "9.99", is_promo=True)]
    return "oliveoil", "l", Decimal("1"), pts


def cosmetic_pasta():
    pts = flat("1.79", 90, 1) + [PricePoint.of(REF, "1.75", is_promo=True)]
    return "pasta", "kg", Decimal("0.5"), pts


def fake_feta():
    pts = flat("6.99", 90, 15) + flat("7.99", 14, 1) + [PricePoint.of(REF, "7.29", is_promo=True)]
    return "feta", "kg", Decimal("0.4"), pts


def real_bananas():
    pts = flat("2.49", 90, 1) + [PricePoint.of(REF, "1.99", is_promo=True)]
    return "bananas", "kg", Decimal("1"), pts


def fake_chicken():
    pts = flat("8.49", 90, 15) + flat("9.49", 14, 1) + [PricePoint.of(REF, "8.99", is_promo=True)]
    return "chicken", "kg", Decimal("1"), pts


def cosmetic_water():
    pts = flat("0.89", 90, 1) + [PricePoint.of(REF, "0.87", is_promo=True)]
    return "water", "l", Decimal("1.5"), pts


def _recent_day_at(series, value) -> str | None:
    if value is None:
        return None
    found = None
    for p in series:
        if p.price == value:
            found = p.day
    return found.isoformat() if found else None


def _reason_code(result, stats) -> str:
    if result.verdict is Verdict.REAL:
        return "real"
    if result.verdict is Verdict.COSMETIC:
        return "cosmetic"
    if result.verdict is Verdict.UNKNOWN:
        return "unknown"
    # FAKE: distinguish "not below the 30-day low" from "equal to usual".
    cheaper = stats.min_30_prior is None or (
        stats.current_price is not None and stats.current_price < stats.min_30_prior
    )
    return "fake_equal" if cheaper else "fake_not_below"


def build_entry(pid, unit_kind, size_base, pts) -> dict:
    chart = build_chart(pts, REF)
    result = evaluate_series(pts, REF, is_promo=True)
    s = chart.stats
    disc = result.discount_vs_median
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return {
        "id": pid,
        "unit_kind": unit_kind,
        "verdict": {Verdict.REAL: "green", Verdict.COSMETIC: "yellow",
                    Verdict.FAKE: "red", Verdict.UNKNOWN: "gray"}[result.verdict],
        "reason_code": _reason_code(result, s),
        "discount_pct": round(float(disc) * 100) if disc is not None else None,
        "current_price": f(s.current_price),
        "current_unit_price": round(float(s.current_price) / float(size_base), 4)
        if s.current_price is not None else None,
        "median_90": f(s.median_90),
        "min_90": f(s.min_90),
        "max_90": f(s.max_90),
        "min_30_prior": f(s.min_30_prior),
        "lowest_day": _recent_day_at(chart.series, s.min_90),
        "highest_day": _recent_day_at(chart.series, s.max_90),
        "series": [{"day": p.day.isoformat(), "price": float(p.price)} for p in chart.series],
    }


# Стълб 2 demo: a fridge scan + desired staples, run through the REAL shopping
# core so the resulting list is genuine, not hand-written. Known products
# (milk/oil/cheese/coffee) link back to стълб 1's verdict.
ID_BG = {
    "milk": "Прясно мляко", "oil": "Олио", "cheese": "Кашкавал", "coffee": "Кафе",
    "eggs": "Яйца", "butter": "Масло", "yogurt": "Кисело мляко",
}


def build_fridge() -> dict:
    recognized = [
        {"id": "milk", "quantity": 1, "unit": "l", "confidence": 0.95},
        {"id": "butter", "quantity": 1, "unit": "pack", "confidence": 0.90},
        {"id": "yogurt", "quantity": 2, "unit": "pcs", "confidence": 0.80},
        {"id": "cheese", "quantity": 1, "unit": "pack", "confidence": 0.70},
    ]
    inventory = merge_inventory(
        [to_inventory_item({**r, "name": ID_BG[r["id"]]}) for r in recognized]
    )
    staples_def = [("milk", 3, "l"), ("oil", 1, "l"), ("eggs", 10, "pcs"),
                   ("coffee", 1, "pack"), ("butter", 1, "pack")]
    unit_by_id = {sid: u for sid, _, u in staples_def}
    staples = [Staple(ID_BG[sid], q, u) for sid, q, u in staples_def]
    bg_to_id = {v: k for k, v in ID_BG.items()}

    shopping = []
    for it in build_shopping_list(inventory, staples):
        sid = bg_to_id[it.name]
        shopping.append({
            "id": sid,
            "needed_quantity": it.needed_quantity,
            "unit": unit_by_id.get(sid),
            "reason_code": "missing" if it.reason.startswith("липсва") else "low",
        })
    return {"recognized": recognized, "shopping": shopping}


def main() -> None:
    scenarios = (
        fake_milk, real_oil, cosmetic_cheese, unknown_coffee,
        real_flour, fake_sugar, cosmetic_bread, cosmetic_rice, real_tomatoes,
        real_oliveoil, cosmetic_pasta, fake_feta, real_bananas, fake_chicken, cosmetic_water,
    )
    products = [build_entry(*sc()) for sc in scenarios]
    payload = {"generated_for": REF.isoformat(), "base_currency": "BGN",
               "products": products, "fridge": build_fridge()}
    out = ROOT / "public" / "data.js"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "window.SAVECHECK_DEMO = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {out} ({len(products)} products)")


if __name__ == "__main__":
    main()
