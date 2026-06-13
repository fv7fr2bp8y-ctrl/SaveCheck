"""SQLAlchemy 2.0 ORM models for the price store.

Design notes:
* ``Product`` is the *canonical* identity used to compare the same item across
  chains ("кисело мляко 400г"). Each chain's own naming is mapped onto it via
  ``ChainProduct``. For the ~101 consumer-basket groups this mapping is small
  and largely pre-categorised by КЗП.
* ``PriceObservation`` is the append-only fact table: one row per
  product/store/day. Everything in ``savecheck.pricing`` is computed from it.

This module requires the ``db`` optional dependencies (SQLAlchemy). It is not
imported by the pure pricing core or its tests.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Chain(Base):
    __tablename__ = "chain"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)

    stores: Mapped[list["Store"]] = relationship(back_populates="chain")


class Store(Base):
    __tablename__ = "store"

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chain.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(120))  # the chain's own store id
    region: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(255))

    chain: Mapped[Chain] = relationship(back_populates="stores")

    __table_args__ = (UniqueConstraint("chain_id", "external_id", name="uq_store_chain_external"),)


class Product(Base):
    """Canonical product identity, shared across chains."""

    __tablename__ = "product"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(120))
    brand: Mapped[str | None] = mapped_column(String(120))
    package_size: Mapped[str | None] = mapped_column(String(60))  # e.g. "400 g", "1 L"
    # The КЗП basket group code this product belongs to, when applicable.
    basket_group: Mapped[str | None] = mapped_column(String(60))


class ChainProduct(Base):
    """Maps a chain's own SKU/name onto a canonical :class:`Product`."""

    __tablename__ = "chain_product"

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chain.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("product.id", ondelete="SET NULL")
    )
    external_id: Mapped[str | None] = mapped_column(String(120))
    raw_name: Mapped[str] = mapped_column(String(255))

    __table_args__ = (
        UniqueConstraint("chain_id", "external_id", name="uq_chainproduct_chain_external"),
    )


class PriceObservation(Base):
    """One observed price for a chain-product at a store on a day (append-only)."""

    __tablename__ = "price_observation"

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_product_id: Mapped[int] = mapped_column(
        ForeignKey("chain_product.id", ondelete="CASCADE")
    )
    store_id: Mapped[int | None] = mapped_column(ForeignKey("store.id", ondelete="SET NULL"))
    observed_on: Mapped[date] = mapped_column(Date)
    price: Mapped[Numeric] = mapped_column(Numeric(10, 2))
    is_promo: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(60), default="kolkostruva")
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "chain_product_id",
            "store_id",
            "observed_on",
            "source",
            name="uq_obs_unique_day",
        ),
    )


class Watch(Base):
    """A user's price alert for one chain-product (the watchlist)."""

    __tablename__ = "watch"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120))
    chain_product_id: Mapped[int] = mapped_column(
        ForeignKey("chain_product.id", ondelete="CASCADE")
    )
    target_price: Mapped[Numeric | None] = mapped_column(Numeric(10, 2))
    notify_on_real_promo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "chain_product_id", name="uq_watch_user_product"),
    )
