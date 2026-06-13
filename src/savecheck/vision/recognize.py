"""Recognise grocery products in a fridge photo with Claude vision.

Uses the official Anthropic Python SDK with a structured (JSON-schema) output so
the model returns a validated list of products rather than free text. The model
is Claude Opus 4.8 (``claude-opus-4-8``).

Requires the ``vision`` optional dependencies (``anthropic``). The pure
post-processing (dedup, normalisation) lives in ``savecheck.shopping`` and is
tested without network access.
"""

from __future__ import annotations

import base64

from pydantic import BaseModel, Field

from ..shopping.inventory import InventoryItem, merge_inventory, to_inventory_item

MODEL = "claude-opus-4-8"

SYSTEM = (
    "Ти си помощник, който разпознава хранителни продукти на снимка от хладилник. "
    "Връщаш само това, което реално се вижда — не предполагай продукти, които не са "
    "на снимката. За всеки продукт давай кратко общо име на български (напр. „прясно "
    "мляко“, „яйца“, „кашкавал“), категория, приблизително количество и мерна единица "
    "(бр, л, кг, опаковка), и увереност между 0 и 1. Ако нещо е скрито или неясно, дай "
    "по-ниска увереност вместо да гадаеш."
)

PROMPT = "Кои хранителни продукти виждаш в този хладилник? Изброй ги структурирано."


class _VisionItem(BaseModel):
    name: str
    category: str | None = None
    quantity: float = Field(default=1)
    unit: str | None = None
    confidence: float = Field(default=0.5)


class _FridgeContents(BaseModel):
    items: list[_VisionItem]


def recognize_fridge(
    image_data: bytes | str,
    media_type: str = "image/jpeg",
    client=None,
) -> list[InventoryItem]:
    """Identify products in a fridge photo and return a clean inventory.

    ``image_data`` may be raw bytes or an already-base64-encoded string.
    ``client`` lets callers/tests inject an ``anthropic.Anthropic`` instance.
    """
    if client is None:
        from anthropic import Anthropic  # lazy: import only when actually calling out

        client = Anthropic()

    b64 = (
        base64.standard_b64encode(image_data).decode("utf-8")
        if isinstance(image_data, bytes)
        else image_data
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        output_format=_FridgeContents,
    )

    contents = response.parsed_output
    items = [to_inventory_item(v.model_dump()) for v in contents.items]
    return merge_inventory(items)
