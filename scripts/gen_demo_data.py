"""Generate the demo dataset for the web preview from REAL KZP price data.

Reads the daily ZIP exports from a local cache directory, builds price histories
for a basket of products across the main BG chains, and writes public/data.js.

    python scripts/gen_demo_data.py [--zip-dir /tmp/kzp_zips]

Output is BGN-denominated; the website applies FX conversion at render time.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from savecheck.ingest.kolkostruva import chain_name_from_filename, parse_chain_csv  # noqa: E402
from savecheck.pricing import PricePoint, Verdict, build_chart, evaluate_series  # noqa: E402
from savecheck.shopping import (  # noqa: E402
    Staple,
    build_shopping_list,
    merge_inventory,
    to_inventory_item,
)

# ---------------------------------------------------------------------------
# Chain mapping: КЗП chain name (after chain_name_from_filename) → display label
# ---------------------------------------------------------------------------
CHAIN_DISPLAY: dict[str, str] = {
    "Лидл България":    "Lidl",
    "Кауфланд България": "Kaufland",
    "Билла":            "Billa",
    "ФАНТАСТИКО":       "Fantastico",
    "T Market":         "T Market",
}
MAIN_CHAINS = set(CHAIN_DISPLAY)

# ---------------------------------------------------------------------------
# Basket: product id → regex matching product names in КЗП data
# ---------------------------------------------------------------------------
BASKET: dict[str, re.Pattern] = {
    "milk":   re.compile(r"прясно мляко.{0,10}(1|1[,.]0)\s*л", re.IGNORECASE),
    "oil":    re.compile(r"слънчогледово\s*(олио|масло).{0,8}(1|1[,.]0)\s*л", re.IGNORECASE),
    "cheese": re.compile(r"кашкавал.{0,30}4[0-9]{2}", re.IGNORECASE),
    "butter": re.compile(r"краве\s*масло.{0,20}(82|250|125)", re.IGNORECASE),
    "sugar":  re.compile(r"\bзахар\b.{0,10}1\s*кг|1\s*кг\s*захар", re.IGNORECASE),
    "flour":  re.compile(r"брашно.{0,25}(тип\s*500|бял|пшен).{0,25}1\s*кг|1\s*кг.{0,10}брашно", re.IGNORECASE),
    "rice":   re.compile(r"\bориз\b(?!.*пюре).{0,20}(1\s*кг|среднозърн|басмати|ризон)", re.IGNORECASE),
    "eggs":   re.compile(r"\bяйца\b.{0,10}10\s*бр|10\s*бр.{0,10}\bяйца\b", re.IGNORECASE),
    "coffee": re.compile(r"(мляно|смляно)\s*кафе", re.IGNORECASE),
    "bread":  re.compile(r"\bхляб\b(?!.*(баниц|тутманик|кашкавалк|кор[ии]|тостер))", re.IGNORECASE),
}

UNIT_INFO: dict[str, tuple[str, Decimal]] = {
    "milk":   ("l",   Decimal("1")),
    "oil":    ("l",   Decimal("1")),
    "cheese": ("kg",  Decimal("0.4")),
    "butter": ("kg",  Decimal("0.25")),
    "sugar":  ("kg",  Decimal("1")),
    "flour":  ("kg",  Decimal("1")),
    "rice":   ("kg",  Decimal("1")),
    "eggs":   ("pcs", Decimal("10")),
    "coffee": ("kg",  Decimal("0.25")),
    "bread":  ("kg",  Decimal("0.7")),
}

REF = date(2026, 6, 13)


# ---------------------------------------------------------------------------
# Loading ZIPs (using main's parse_chain_csv + chain_name_from_filename)
# ---------------------------------------------------------------------------

def load_all_zips(zip_dir: Path) -> dict[str, dict[str, list[PricePoint]]]:
    """Return {product_id: {display_chain: [PricePoint, ...]}} from all ZIPs."""
    series: dict[str, dict[str, list[PricePoint]]] = {
        pid: defaultdict(list) for pid in BASKET
    }

    zips = sorted(zip_dir.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(f"No ZIP files found in {zip_dir}")

    for zip_path in zips:
        try:
            d = date.fromisoformat(zip_path.stem)
        except ValueError:
            continue

        print(f"  {zip_path.name}…", end="", flush=True)
        count = 0

        with zipfile.ZipFile(zip_path) as zf:
            for entry in zf.namelist():
                if not entry.lower().endswith(".csv"):
                    continue
                chain_raw = chain_name_from_filename(entry)
                if chain_raw not in MAIN_CHAINS:
                    continue
                display = CHAIN_DISPLAY[chain_raw]

                day_best: dict[str, Decimal] = {}  # product_id → best price this day
                with zf.open(entry) as raw:
                    csv_bytes = raw.read()
                for row in parse_chain_csv(csv_bytes, chain_raw, d):
                    if row.price <= 0:
                        continue
                    for pid, pat in BASKET.items():
                        if pat.search(row.product_name):
                            existing = day_best.get(pid)
                            if existing is None or row.price < existing:
                                day_best[pid] = row.price
                            count += 1
                            break

                for pid, price in day_best.items():
                    series[pid][display].append(PricePoint(day=d, price=price))

        print(f" {count} hits")

    return series


# ---------------------------------------------------------------------------
# Building product entries
# ---------------------------------------------------------------------------

PRIMARY_ORDER = ["Lidl", "Kaufland", "Billa", "Fantastico", "T Market"]


def _reason_code(result, stats) -> str:
    if result.verdict is Verdict.REAL:
        return "real"
    if result.verdict is Verdict.COSMETIC:
        return "cosmetic"
    if result.verdict is Verdict.UNKNOWN:
        return "unknown"
    cheaper = stats.min_30_prior is None or (
        stats.current_price is not None and stats.current_price < stats.min_30_prior
    )
    return "fake_equal" if cheaper else "fake_not_below"


def _recent_day_at(chart_series, value) -> str | None:
    if value is None:
        return None
    found = None
    for p in chart_series:
        if p.price == value:
            found = p.day
    return found.isoformat() if found else None


def build_entry(pid: str, chain_series: dict[str, list[PricePoint]]) -> dict | None:
    unit_kind, size_base = UNIT_INFO[pid]
    f = lambda v: float(v) if v is not None else None  # noqa: E731

    primary = next((c for c in PRIMARY_ORDER if chain_series.get(c)), None)
    if primary is None:
        print(f"  WARNING: no data for {pid}")
        return None

    pts = sorted(chain_series[primary], key=lambda p: p.day)
    if len(pts) < 3:
        print(f"  WARNING: too few points for {pid}/{primary}: {len(pts)}")
        return None

    # Determine promo flag from price signal (current < prior 30-day min)
    result = evaluate_series(pts, REF, is_promo=False)
    s = result.stats
    is_promo = bool(
        s.current_price and s.min_30_prior and s.current_price < s.min_30_prior
    )
    result = evaluate_series(pts, REF, is_promo=is_promo)
    s = result.stats
    chart = build_chart(pts, REF)
    disc = result.discount_vs_median

    # Real chain prices for the "offers" section
    offers = []
    for c in PRIMARY_ORDER:
        cpts = chain_series.get(c, [])
        today = [p for p in cpts if p.day == REF]
        if not today:
            recent = [p for p in cpts if p.day >= REF - timedelta(days=3)]
            if not recent:
                continue
            today = [max(recent, key=lambda p: p.day)]
        offers.append({"chain": c, "price": float(min(p.price for p in today))})
    offers.sort(key=lambda o: o["price"])

    return {
        "id": pid,
        "unit_kind": unit_kind,
        "verdict": {
            Verdict.REAL: "green", Verdict.COSMETIC: "yellow",
            Verdict.FAKE: "red",  Verdict.UNKNOWN: "gray",
        }[result.verdict],
        "reason_code": _reason_code(result, s),
        "discount_pct": round(float(disc) * 100) if disc is not None else None,
        "current_price": f(s.current_price),
        "current_unit_price": (
            round(float(s.current_price) / float(size_base), 4)
            if s.current_price is not None else None
        ),
        "median_90": f(s.median_90),
        "min_90": f(s.min_90),
        "max_90": f(s.max_90),
        "min_30_prior": f(s.min_30_prior),
        "lowest_day": _recent_day_at(chart.series, s.min_90),
        "highest_day": _recent_day_at(chart.series, s.max_90),
        "series": [{"day": p.day.isoformat(), "price": float(p.price)} for p in chart.series],
        "offers": offers,
    }


# ---------------------------------------------------------------------------
# Стълб 2 — fridge demo (synthetic; vision requires a real camera)
# ---------------------------------------------------------------------------
ID_BG = {
    "milk": "Прясно мляко", "oil": "Олио", "cheese": "Кашкавал", "coffee": "Кафе",
    "eggs": "Яйца", "butter": "Масло", "yogurt": "Кисело мляко",
}


def build_fridge() -> dict:
    recognized = [
        {"id": "milk",   "quantity": 1, "unit": "l",    "confidence": 0.95},
        {"id": "butter", "quantity": 1, "unit": "pack", "confidence": 0.90},
        {"id": "yogurt", "quantity": 2, "unit": "pcs",  "confidence": 0.80},
        {"id": "cheese", "quantity": 1, "unit": "pack", "confidence": 0.70},
    ]
    inventory = merge_inventory(
        [to_inventory_item({**r, "name": ID_BG[r["id"]]}) for r in recognized]
    )
    staples_def = [
        ("milk",   3,  "l"),
        ("oil",    1,  "l"),
        ("eggs",   10, "pcs"),
        ("coffee", 1,  "pack"),
        ("butter", 1,  "pack"),
    ]
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


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip-dir", default="/tmp/kzp_zips",
                        help="Directory with YYYY-MM-DD.zip files (default: /tmp/kzp_zips)")
    args = parser.parse_args()

    zip_dir = Path(args.zip_dir)
    print(f"Loading ZIPs from {zip_dir} …")
    series = load_all_zips(zip_dir)

    products = []
    for pid in BASKET:
        entry = build_entry(pid, series[pid])
        if entry:
            products.append(entry)
            chains_str = ", ".join(f"{o['chain']} {o['price']:.2f}" for o in entry["offers"])
            print(f"  {pid:<10} {entry['verdict']:<7} {entry['current_price']:.2f} BGN  [{chains_str}]")

    payload = {
        "generated_for": REF.isoformat(),
        "base_currency": "BGN",
        "products": products,
        "fridge": build_fridge(),
    }

    out = ROOT / "public" / "data.js"
    out.write_text(
        "window.SAVECHECK_DEMO = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(f"\nWrote {out}  ({len(products)} products)")


if __name__ == "__main__":
    main()
