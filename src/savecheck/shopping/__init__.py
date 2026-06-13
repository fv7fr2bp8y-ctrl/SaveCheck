"""Pure shopping-list logic for стълб 2 (fridge photo → shopping list).

Stdlib only, so it is unit-testable without the vision model, network, or any
third-party package. The vision layer (``savecheck.vision``) produces
``InventoryItem``s; everything here is deterministic post-processing.
"""

from .inventory import InventoryItem, merge_inventory, normalize, to_inventory_item
from .staples import Staple
from .shopping_list import ShoppingItem, build_shopping_list

__all__ = [
    "InventoryItem",
    "merge_inventory",
    "normalize",
    "to_inventory_item",
    "Staple",
    "ShoppingItem",
    "build_shopping_list",
]
