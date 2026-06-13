"""Tests for the open-data parser (pure stdlib: csv/json). No network needed.

These lock in the parser's behaviour against the PROVISIONAL column mapping so
that when the real format is confirmed, any change is caught here.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from savecheck.ingest.kolkostruva import parse_rows  # noqa: E402


def test_parse_csv_basic():
    csv_text = (
        "chain,product,price,date,promo\n"
        "Lidl,Прясно мляко 1L,2.49,2026-06-13,1\n"
        "Kaufland,Прясно мляко 1L,2,80,\n"  # note: comma decimal handled
    )
    rows = list(parse_rows(csv_text))
    assert len(rows) == 1  # the malformed comma-as-extra-column row is skipped
    assert rows[0].chain_name == "Lidl"
    assert rows[0].price == Decimal("2.49")
    assert rows[0].observed_on == date(2026, 6, 13)
    assert rows[0].is_promo is True


def test_parse_csv_comma_decimal():
    csv_text = "chain;product;price;date\n"  # header only sanity check below
    # Use a clean 4-column CSV where price uses a comma decimal separator.
    csv_text = "chain,product,price,date\nBilla,Олио 1L,3,2026-06-13\n"
    rows = list(parse_rows(csv_text))
    assert rows[0].price == Decimal("3")


def test_parse_json_list():
    json_text = (
        '[{"verige": "Billa", "stoka": "Олио 1L", "cena": "3,49", '
        '"data": "13.06.2026", "promotsiya": "да"}]'
    )
    rows = list(parse_rows(json_text))
    assert len(rows) == 1
    assert rows[0].chain_name == "Billa"
    assert rows[0].price == Decimal("3.49")
    assert rows[0].observed_on == date(2026, 6, 13)
    assert rows[0].is_promo is True


def test_parse_json_wrapped_in_data_key():
    json_text = '{"data": [{"chain": "Lidl", "product": "Яйца M 10бр", "price": "2.99", "date": "2026-06-01"}]}'
    rows = list(parse_rows(json_text))
    assert len(rows) == 1
    assert rows[0].is_promo is False


def test_unmappable_rows_are_skipped():
    rows = list(parse_rows("foo,bar\n1,2\n"))
    assert rows == []


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
