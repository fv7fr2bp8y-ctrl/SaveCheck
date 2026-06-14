"""Ingest the real КЗП "Колко струва" open-data export.

The official export (kolkostruva.bg/opendata) is a ZIP with **one CSV per
retail chain**, named like ``Лидл България_131071587.csv`` /
``ФАНТАСТИКО (ФАНТАСТИКО ГРУП ООД)_206255903.csv`` (display name, optional legal
entity in parentheses, ``_<ЕИК>`` suffix). Each CSV is quoted, comma-delimited
UTF-8 with this header:

    "Населено място","Търговски обект","Наименование на продукта",
    "Код на продукта","Категория","Цена на дребно","Цена в промоция"

Two fields live *outside* the rows:
* the **chain** comes from the file name, and
* the **date** comes from the export (the ZIP name / the day you downloaded it).

"Цена в промоция" is empty unless the item is on promotion; when present it is
the price the shopper pays, and we mark the observation ``is_promo``.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from ..config import settings

# Exact КЗП column headers.
COL_REGION = "Населено място"
COL_STORE = "Търговски обект"
COL_NAME = "Наименование на продукта"
COL_CODE = "Код на продукта"
COL_CATEGORY = "Категория"
COL_RETAIL = "Цена на дребно"
COL_PROMO = "Цена в промоция"


@dataclass(frozen=True)
class RawPriceRow:
    chain_name: str
    product_name: str
    price: Decimal  # the promo price when on promotion, else the retail price
    observed_on: date
    is_promo: bool = False
    retail_price: Decimal | None = None
    store: str | None = None
    region: str | None = None
    product_code: str | None = None
    category: str | None = None


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None


def chain_name_from_filename(name: str) -> str:
    """``"ФАНТАСТИКО (ФАНТАСТИКО ГРУП ООД)_206255903.csv"`` -> ``"ФАНТАСТИКО"``."""
    stem = Path(name).stem
    stem = re.sub(r"_\d+$", "", stem)  # drop the _<ЕИК> suffix
    stem = re.split(r"\s*\(", stem, maxsplit=1)[0]  # drop the legal-entity parenthetical
    return stem.strip()


def parse_chain_csv(
    content: bytes | str, chain_name: str, observed_on: date
) -> Iterator[RawPriceRow]:
    """Parse one chain's КЗП CSV into normalised rows."""
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        name = (r.get(COL_NAME) or "").strip()
        retail = _to_decimal(r.get(COL_RETAIL))
        promo = _to_decimal(r.get(COL_PROMO))
        price = promo if promo is not None else retail
        if not name or price is None:
            continue
        yield RawPriceRow(
            chain_name=chain_name,
            product_name=name,
            price=price,
            observed_on=observed_on,
            is_promo=promo is not None,
            retail_price=retail,
            store=(r.get(COL_STORE) or None),
            region=(r.get(COL_REGION) or None),
            product_code=(r.get(COL_CODE) or None),
            category=(r.get(COL_CATEGORY) or None),
        )


def parse_export(directory: str | Path, observed_on: date) -> Iterator[RawPriceRow]:
    """Parse every ``*.csv`` in an unzipped КЗП export directory.

    The chain name is derived from each file name; ``observed_on`` is the export
    date (the ZIP is one day's snapshot).
    """
    for csv_path in sorted(Path(directory).glob("*.csv")):
        chain = chain_name_from_filename(csv_path.name)
        yield from parse_chain_csv(csv_path.read_bytes(), chain, observed_on)


def fetch_opendata(day: date, base_url: str | None = None) -> bytes:
    """Download the export ZIP for ``day``.

    URL (confirmed): https://kolkostruva.bg/opendata_files/YYYY-MM-DD.zip
    The server requires a browser-like User-Agent (returns 403 otherwise).
    """
    import httpx  # imported lazily so the module loads without the 'ingest' extra

    base = (base_url or settings.kolkostruva_base_url).rstrip("/")
    url = f"{base}/{day.isoformat()}.zip"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SaveCheck/1.0)"}
    resp = httpx.get(url, headers=headers, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content
