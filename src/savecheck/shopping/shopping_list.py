"""Turn (fridge inventory + desired staples) into a shopping list."""

from __future__ import annotations

from dataclasses import dataclass

from .inventory import InventoryItem, normalize
from .staples import Staple


@dataclass(frozen=True)
class ShoppingItem:
    name: str
    needed_quantity: float
    unit: str | None
    reason: str  # user-facing (Bulgarian): "липсва" / "свършва (остава …)"


def _fmt(value: float) -> str:
    """Drop a trailing .0 so '2.0' reads as '2'."""
    return str(int(value)) if value == int(value) else str(round(value, 2))


def build_shopping_list(
    inventory: list[InventoryItem],
    staples: list[Staple],
    min_confidence: float = 0.0,
) -> list[ShoppingItem]:
    """What to buy: staples that are missing or below their desired quantity.

    ``min_confidence`` ignores shaky detections — if the model is only 20% sure
    it saw milk, we don't let that silently cancel a "buy milk" entry.
    """
    on_hand = {
        normalize(i.name): i for i in inventory if i.confidence >= min_confidence
    }

    out: list[ShoppingItem] = []
    for staple in staples:
        item = on_hand.get(normalize(staple.name))
        have = item.quantity if item is not None else 0.0

        if have <= 0:
            out.append(
                ShoppingItem(staple.name, staple.desired_quantity, staple.unit, "липсва")
            )
        elif have < staple.desired_quantity:
            out.append(
                ShoppingItem(
                    staple.name,
                    round(staple.desired_quantity - have, 2),
                    staple.unit,
                    f"свършва (остава {_fmt(have)})",
                )
            )
    return out
