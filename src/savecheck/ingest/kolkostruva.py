"""Ingest official open price data from the КЗП "Колко струва" portal.

Source: https://kolkostruva.bg/opendata — the state portal where chains with
turnover over 10M BGN are legally required to publish daily prices for the ~101
consumer-basket product groups, including a promo flag. It exposes downloadable
open-data files per date plus a historical archive (which lets us backfill the
90-day window on day one).

STATUS: the exact file format (CSV vs JSON) and column names are PROVISIONAL.
The host is not reachable from the current sandbox (network egress allowlist),
so the field mapping in ``COLUMN_MAP`` is a best guess. Once the host is
allowlisted, download one sample file and finalise ``COLUMN_MAP`` / the format
sniffing in ``parse_rows`` — the rest of the pipeline stays the same.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, Iterator

from ..config import settings


@dataclass(frozen=True)
class RawPriceRow:
    """A normalised row, decoupled from the source file's exact shape."""

    chain_name: str
    product_name: str
    price: Decimal
    observed_on: date
    is_promo: bool = False
    store_external_id: str | None = None
    region: str | None = None
    product_external_id: str | None = None
    basket_group: str | None = None


# PROVISIONAL mapping from source field names -> RawPriceRow fields. Multiple
# candidates per field because the published column names are not yet confirmed.
COLUMN_MAP: dict[str, tuple[str, ...]] = {
    "chain_name": ("chain", "verige", "targovska_veriga", "merchant"),
    "product_name": ("product", "stoka", "naименование", "name"),
    "price": ("price", "cena", "edinichna_cena"),
    "observed_on": ("date", "data", "den"),
    "is_promo": ("promo", "promotsiya", "is_promo"),
    "store_external_id": ("store_id", "obekt_id", "obekt"),
    "region": ("region", "oblast"),
    "product_external_id": ("product_id", "stoka_id", "ean", "barcode"),
    "basket_group": ("group", "grupa", "kosnitsa_grupa"),
}

_TRUE = {"1", "true", "da", "да", "yes", "y", "promo"}


def _pick(row: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for key in candidates:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None


def _to_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _row_from_mapping(row: dict[str, str]) -> RawPriceRow | None:
    """Map one source dict onto a RawPriceRow, skipping unusable rows."""
    chain = _pick(row, COLUMN_MAP["chain_name"])
    product = _pick(row, COLUMN_MAP["product_name"])
    price = _to_decimal(_pick(row, COLUMN_MAP["price"]))
    observed = _to_date(_pick(row, COLUMN_MAP["observed_on"]))
    if not (chain and product and price is not None and observed is not None):
        return None
    promo_raw = (_pick(row, COLUMN_MAP["is_promo"]) or "").strip().lower()
    return RawPriceRow(
        chain_name=chain.strip(),
        product_name=product.strip(),
        price=price,
        observed_on=observed,
        is_promo=promo_raw in _TRUE,
        store_external_id=_pick(row, COLUMN_MAP["store_external_id"]),
        region=_pick(row, COLUMN_MAP["region"]),
        product_external_id=_pick(row, COLUMN_MAP["product_external_id"]),
        basket_group=_pick(row, COLUMN_MAP["basket_group"]),
    )


def parse_rows(content: bytes | str) -> Iterator[RawPriceRow]:
    """Parse a downloaded open-data file (CSV or JSON) into RawPriceRows.

    Format is sniffed: a leading ``[`` or ``{`` is treated as JSON, otherwise
    CSV. Both paths funnel through ``_row_from_mapping`` so the column mapping
    lives in exactly one place.
    """
    text = content.decode("utf-8") if isinstance(content, bytes) else content
    stripped = text.lstrip()

    if stripped.startswith("[") or stripped.startswith("{"):
        data = json.loads(text)
        records: Iterable = data if isinstance(data, list) else data.get("data", [])
        for rec in records:
            if isinstance(rec, dict):
                mapped = _row_from_mapping({str(k): v for k, v in rec.items()})
                if mapped:
                    yield mapped
        return

    reader = csv.DictReader(io.StringIO(text))
    for rec in reader:
        mapped = _row_from_mapping({str(k): (v or "") for k, v in rec.items()})
        if mapped:
            yield mapped


def fetch_opendata(day: date, base_url: str | None = None) -> bytes:
    """Download the open-data file for ``day``.

    PROVISIONAL: the URL shape is a guess (``{base}?date=YYYY-MM-DD``). Confirm
    the real endpoint once the host is reachable, then adjust here only.
    """
    import httpx  # imported lazily so the module loads without the 'ingest' extra

    url = base_url or settings.kolkostruva_base_url
    resp = httpx.get(url, params={"date": day.isoformat()}, timeout=60.0)
    resp.raise_for_status()
    return resp.content
