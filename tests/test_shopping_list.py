"""Tests for the стълб 2 shopping core. Pure stdlib; no vision model needed."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from savecheck.shopping import (  # noqa: E402
    InventoryItem,
    Staple,
    build_shopping_list,
    merge_inventory,
    normalize,
    to_inventory_item,
)


def inv(name, qty=1.0, conf=0.9, unit=None, cat=None):
    return InventoryItem(name=name, category=cat, quantity=qty, unit=unit, confidence=conf)


def test_to_inventory_item_coerces_loose_fields():
    item = to_inventory_item({"name": " Прясно мляко ", "quantity": "2", "confidence": "1.4"})
    assert item.name == "Прясно мляко"
    assert item.quantity == 2.0
    assert item.confidence == 1.0  # clamped to [0,1]


def test_to_inventory_item_defaults_bad_quantity():
    item = to_inventory_item({"name": "Яйца", "quantity": "n/a"})
    assert item.quantity == 1.0
    assert item.confidence == 0.5


def test_normalize_matches_case_and_whitespace():
    assert normalize("  Прясно   Мляко ") == normalize("прясно мляко")


def test_merge_inventory_sums_duplicates():
    merged = merge_inventory([inv("Кисело мляко", 1), inv("кисело мляко", 2, conf=0.6)])
    assert len(merged) == 1
    assert merged[0].quantity == 3
    assert merged[0].confidence == 0.9  # keeps the best


def test_merge_inventory_drops_nameless():
    assert merge_inventory([inv("", 5)]) == []


def test_missing_staple_goes_on_list():
    items = build_shopping_list([], [Staple("Олио", 1, "л")])
    assert len(items) == 1
    assert items[0].reason == "липсва"
    assert items[0].needed_quantity == 1


def test_low_staple_lists_only_the_deficit():
    items = build_shopping_list([inv("Яйца", 4, unit="бр")], [Staple("Яйца", 10, "бр")])
    assert items[0].needed_quantity == 6
    assert "остава 4" in items[0].reason


def test_sufficient_staple_is_omitted():
    items = build_shopping_list([inv("Мляко", 3, unit="л")], [Staple("Мляко", 2, "л")])
    assert items == []


def test_low_confidence_detection_is_ignored():
    # Model is only 20% sure it saw milk -> we still buy milk.
    items = build_shopping_list(
        [inv("Мляко", 5, conf=0.2)], [Staple("Мляко", 2, "л")], min_confidence=0.5
    )
    assert len(items) == 1
    assert items[0].reason == "липсва"


def test_full_flow_recognition_to_list():
    raw = [
        {"name": "Прясно мляко", "quantity": 1, "confidence": 0.95, "unit": "л"},
        {"name": "прясно мляко", "quantity": 1, "confidence": 0.4, "unit": "л"},  # dup
        {"name": "Масло", "quantity": 1, "confidence": 0.9},
    ]
    inventory = merge_inventory([to_inventory_item(r) for r in raw])
    staples = [Staple("Прясно мляко", 3, "л"), Staple("Яйца", 10, "бр"), Staple("Масло", 1)]
    items = build_shopping_list(inventory, staples)
    names = {i.name: i for i in items}
    assert set(names) == {"Прясно мляко", "Яйца"}  # maslo sufficient, milk low, eggs missing
    assert names["Прясно мляко"].needed_quantity == 1  # 3 desired - 2 detected


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
