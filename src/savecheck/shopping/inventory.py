"""What the AI sees in the fridge, normalised into a clean inventory."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InventoryItem:
    """One recognised product currently in the fridge."""

    name: str
    category: str | None
    quantity: float  # estimated count or amount (e.g. 2 cartons, 0.5 kg)
    unit: str | None  # "бр", "л", "кг", "опаковка", …
    confidence: float  # 0..1, how sure the model is


def normalize(name: str) -> str:
    """Collapse whitespace and case for name matching (e.g. inventory ↔ staple)."""
    return " ".join(name.strip().lower().split())


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_inventory_item(raw: dict) -> InventoryItem:
    """Build an InventoryItem from a loose dict (e.g. a vision model row).

    Defensive on purpose: the vision output is model-generated, so quantities,
    confidences and missing fields are coerced rather than trusted.
    """
    qty = _to_float(raw.get("quantity"), 1.0)
    conf = min(1.0, max(0.0, _to_float(raw.get("confidence"), 0.5)))
    return InventoryItem(
        name=str(raw.get("name") or "").strip(),
        category=(raw.get("category") or None),
        quantity=qty if qty > 0 else 1.0,
        unit=(raw.get("unit") or None),
        confidence=conf,
    )


def merge_inventory(items: list[InventoryItem]) -> list[InventoryItem]:
    """Deduplicate by normalised name: sum quantities, keep the best confidence.

    The model often detects the same product more than once (two yoghurt cups,
    a bottle seen from two angles); collapse those into one line.
    """
    by_name: dict[str, InventoryItem] = {}
    for item in items:
        if not item.name:
            continue
        key = normalize(item.name)
        cur = by_name.get(key)
        if cur is None:
            by_name[key] = item
        else:
            by_name[key] = InventoryItem(
                name=cur.name,
                category=cur.category or item.category,
                quantity=cur.quantity + item.quantity,
                unit=cur.unit or item.unit,
                confidence=max(cur.confidence, item.confidence),
            )
    return list(by_name.values())
