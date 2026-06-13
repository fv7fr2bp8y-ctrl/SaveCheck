"""FastAPI app exposing the promotion verdict for a chain-product.

Requires the ``api`` and ``db`` optional dependencies. Run with:
    uvicorn savecheck.api.main:app --reload
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import SessionLocal, load_points, resolve_chain_product
from ..pricing.history import build_chart
from ..pricing.verdict import evaluate_series
from ..shopping import InventoryItem, Staple, build_shopping_list

app = FastAPI(title="SaveCheck API", version="0.1.0")


def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/verdict")
def verdict(
    chain_product_id: int = Query(..., description="ID of the chain-product to evaluate"),
    is_promo: bool = Query(False, description="Is the item currently advertised as a promo?"),
    current_price: float | None = Query(
        None, description="Override price under evaluation (e.g. the scanned tag price)"
    ),
    on: date | None = Query(None, description="Reference day; defaults to today"),
    session: Session = Depends(get_session),
) -> dict:
    """Return the traffic-light verdict plus the data behind the chart."""
    if resolve_chain_product(session, chain_product_id) is None:
        raise HTTPException(status_code=404, detail="chain_product not found")

    reference_day = on or date.today()
    points = load_points(session, chain_product_id, reference_day)
    result = evaluate_series(
        points,
        reference_day=reference_day,
        is_promo=is_promo,
        current_price=Decimal(str(current_price)) if current_price is not None else None,
    )

    s = result.stats
    return {
        "verdict": result.verdict.value,
        "reason": result.reason,
        "discount_vs_median": (
            float(result.discount_vs_median) if result.discount_vs_median is not None else None
        ),
        "stats": _stats_dict(s),
    }


@app.get("/history")
def history(
    chain_product_id: int = Query(..., description="ID of the chain-product"),
    on: date | None = Query(None, description="Reference day; defaults to today"),
    session: Session = Depends(get_session),
) -> dict:
    """Return the 90-day daily series plus marker lines for the chart."""
    if resolve_chain_product(session, chain_product_id) is None:
        raise HTTPException(status_code=404, detail="chain_product not found")

    reference_day = on or date.today()
    points = load_points(session, chain_product_id, reference_day)
    chart = build_chart(points, reference_day)

    return {
        "floor_day": chart.floor_day.isoformat() if chart.floor_day else None,
        "stats": _stats_dict(chart.stats),
        "series": [
            {"day": p.day.isoformat(), "price": float(p.price), "is_promo": p.is_promo}
            for p in chart.series
        ],
    }


class _InventoryIn(BaseModel):
    name: str
    quantity: float = 1
    unit: str | None = None
    category: str | None = None
    confidence: float = 1.0


class _StapleIn(BaseModel):
    name: str
    desired_quantity: float
    unit: str | None = None
    category: str | None = None


class _ShoppingListRequest(BaseModel):
    inventory: list[_InventoryIn] = []
    staples: list[_StapleIn]
    min_confidence: float = 0.0


@app.post("/shopping-list")
def shopping_list(req: _ShoppingListRequest) -> dict:
    """Стълб 2: given a recognised fridge inventory + desired staples, what to buy.

    Pure logic — no model call. Pair with ``savecheck.vision.recognize_fridge``
    to produce the inventory from a photo.
    """
    inventory = [
        InventoryItem(i.name, i.category, i.quantity, i.unit, i.confidence)
        for i in req.inventory
    ]
    staples = [Staple(s.name, s.desired_quantity, s.unit, s.category) for s in req.staples]
    items = build_shopping_list(inventory, staples, min_confidence=req.min_confidence)
    return {
        "items": [
            {"name": it.name, "needed_quantity": it.needed_quantity, "unit": it.unit, "reason": it.reason}
            for it in items
        ]
    }


def _stats_dict(s) -> dict:
    return {
        "reference_day": s.reference_day.isoformat(),
        "current_price": float(s.current_price) if s.current_price is not None else None,
        "median_90": float(s.median_90) if s.median_90 is not None else None,
        "min_90": float(s.min_90) if s.min_90 is not None else None,
        "max_90": float(s.max_90) if s.max_90 is not None else None,
        "min_30_prior": float(s.min_30_prior) if s.min_30_prior is not None else None,
        "sample_size_90": s.sample_size_90,
    }
