"""Database engine/session setup and a thin repository for the pricing core.

Requires the ``db`` optional dependencies (SQLAlchemy + psycopg). Not imported
by the pure pricing core or its tests.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import ChainProduct, PriceObservation
from .pricing.aggregates import WINDOW_DAYS, PricePoint

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def load_points(
    session: Session,
    chain_product_id: int,
    reference_day: date,
    window_days: int = WINDOW_DAYS,
) -> list[PricePoint]:
    """Load the observations needed to judge one product at one chain.

    Returns a flat list of :class:`PricePoint` the pure core can consume, so the
    DB layer and the pricing logic stay fully decoupled.
    """
    start = reference_day - timedelta(days=window_days)
    stmt = (
        select(
            PriceObservation.observed_on,
            PriceObservation.price,
            PriceObservation.is_promo,
        )
        .where(PriceObservation.chain_product_id == chain_product_id)
        .where(PriceObservation.observed_on >= start)
        .where(PriceObservation.observed_on <= reference_day)
    )
    return [
        PricePoint(day=row.observed_on, price=row.price, is_promo=row.is_promo)
        for row in session.execute(stmt)
    ]


def resolve_chain_product(session: Session, chain_product_id: int) -> ChainProduct | None:
    return session.get(ChainProduct, chain_product_id)
