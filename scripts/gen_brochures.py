"""Generate per-chain promotional brochure summaries with Omnibus verdicts.

Reads the latest KZP ZIP, extracts ALL products with "Цена в промоция" filled,
deduplicates by product code, runs the Omnibus verdict on known basket items,
and writes public/brochures.js.

    python scripts/gen_brochures.py [--zip-dir /tmp/kzp_zips]
"""

from __future__ import annotations

import json
import sys
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from savecheck.ingest.kolkostruva import chain_name_from_filename, parse_chain_csv  # noqa: E402
from savecheck.pricing import PricePoint, Verdict, evaluate_series  # noqa: E402

# Reuse basket + chain config from gen_demo_data.
sys.path.insert(0, str(ROOT / "scripts"))
from gen_demo_data import BASKET, CHAIN_DISPLAY, MAIN_CHAINS, PRIMARY_ORDER, load_all_zips  # noqa: E402

import argparse

REF = date(2026, 6, 13)
MAX_ITEMS_PER_CHAIN = 80  # cap to keep brochures.js small


def _claimed_pct(retail: Decimal | None, promo: Decimal) -> int | None:
    if retail and retail > promo and retail > 0:
        return round(float((retail - promo) / retail * 100))
    return None


def extract_chain_promos(
    zip_path: Path,
    ref: date,
    basket_series: dict[str, dict[str, list[PricePoint]]],
) -> dict[str, list[dict]]:
    """Return {display_chain: [item, ...]} for all promo products in the ZIP."""
    result: dict[str, dict[str, dict]] = defaultdict(dict)  # chain → code/name → data

    with zipfile.ZipFile(zip_path) as zf:
        for entry in zf.namelist():
            if not entry.lower().endswith(".csv"):
                continue
            chain_raw = chain_name_from_filename(entry)
            if chain_raw not in MAIN_CHAINS:
                continue
            display = CHAIN_DISPLAY[chain_raw]

            with zf.open(entry) as raw:
                csv_bytes = raw.read()

            for row in parse_chain_csv(csv_bytes, chain_raw, ref):
                if not row.is_promo or row.price <= 0:
                    continue
                key = row.product_code or row.product_name
                existing = result[display].get(key)
                if existing is None or row.price < existing["price"]:
                    result[display][key] = {
                        "name": row.product_name,
                        "price": row.price,
                        "retail": row.retail_price,
                        "category": row.category or "",
                        "code": row.product_code or "",
                    }

    out: dict[str, list[dict]] = {}
    for c in PRIMARY_ORDER:
        if c not in result:
            continue
        items = []
        for d in result[c].values():
            promo_price: Decimal = d["price"]
            retail_price: Decimal | None = d["retail"]
            claimed = _claimed_pct(retail_price, promo_price)

            item: dict = {
                "name": d["name"],
                "price": float(promo_price),
                "retail": float(retail_price) if retail_price else None,
                "claimed_pct": claimed,
                "category": d["category"],
            }

            # Omnibus verdict for basket products
            for pid, pat in BASKET.items():
                if pat.search(d["name"]):
                    pts_for_chain = basket_series.get(pid, {}).get(c, [])
                    if pts_for_chain:
                        pts = sorted(pts_for_chain, key=lambda p: p.day)
                        today_pts = [p for p in pts if p.day == ref]
                        is_promo_today = any(p.is_promo for p in today_pts)
                        res = evaluate_series(pts, ref, is_promo=is_promo_today)
                        s = res.stats
                        item["basket_id"] = pid
                        item["verdict"] = res.verdict.value
                        item["omnibus_pct"] = (
                            round(float(res.discount_vs_median) * 100)
                            if res.discount_vs_median is not None else None
                        )
                        item["min_30_prior"] = float(s.min_30_prior) if s.min_30_prior else None
                        item["median_90"] = float(s.median_90) if s.median_90 else None
                    break

            items.append(item)

        # Sort: basket RED first (warnings!), basket GREEN second, then by claimed_pct desc
        def _sort(it: dict) -> tuple:
            v = it.get("verdict")
            verdict_rank = {"red": 0, "green": 1, "gray": 2, "yellow": 3}.get(v, 9) if v else 10
            is_basket = 0 if "basket_id" in it else 1
            return (is_basket, verdict_rank, -(it.get("claimed_pct") or 0))

        items.sort(key=_sort)
        out[c] = items[:MAX_ITEMS_PER_CHAIN]

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip-dir", default="/tmp/kzp_zips")
    args = parser.parse_args()

    zip_dir = Path(args.zip_dir)
    zips = sorted(zip_dir.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(f"No ZIPs in {zip_dir}")

    # Use latest available ZIP
    latest_zip = zips[-1]
    ref = date.fromisoformat(latest_zip.stem)

    print(f"Loading 90-day basket series for Omnibus verdicts…")
    basket_series = load_all_zips(zip_dir)

    print(f"Extracting promos from {latest_zip.name}…")
    chains_data = extract_chain_promos(latest_zip, ref, basket_series)

    # Week label: ref through the Sunday of ref's week
    week_end = ref + timedelta(days=6 - ref.weekday())
    week_label = f"{ref.strftime('%-d.%-m')} – {week_end.strftime('%-d.%-m.%Y')}"

    payload = {
        "for_date": ref.isoformat(),
        "week_label": week_label,
        "chains": [
            {
                "chain": c,
                "total_promos": len(chains_data.get(c, [])),
                "items": chains_data.get(c, []),
            }
            for c in PRIMARY_ORDER if c in chains_data
        ],
    }

    out = ROOT / "public" / "brochures.js"
    out.write_text(
        "window.SAVECHECK_BROCHURES = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(f"\nWrote {out}")
    for c in PRIMARY_ORDER:
        if c in chains_data:
            n = len(chains_data[c])
            basket_n = sum(1 for it in chains_data[c] if "basket_id" in it)
            fake_n = sum(1 for it in chains_data[c] if it.get("verdict") == "red")
            real_n = sum(1 for it in chains_data[c] if it.get("verdict") == "green")
            print(f"  {c:<12} {n:>4} promos  (basket: {basket_n} → 🟢{real_n} 🔴{fake_n})")


if __name__ == "__main__":
    main()
