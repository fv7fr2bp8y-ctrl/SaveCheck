"""The household's desired stock — what should always be in the fridge."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Staple:
    """A product the household wants to keep on hand, and how much."""

    name: str
    desired_quantity: float
    unit: str | None = None
    category: str | None = None
