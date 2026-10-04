from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, TIMESTAMP, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from esl.db import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    square_location_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    api_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    variations: Mapped[list["CatalogVariation"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class CatalogVariation(Base):
    __tablename__ = "catalog_variations"
    __table_args__ = (Index("catalog_variations_item_id", "item_id"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    item_id: Mapped[str] = mapped_column(
        Text, ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False
    )
    variation_name: Mapped[str] = mapped_column(Text, nullable=False)
    sku: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int | None] = mapped_column(Integer)
    # ISO 4217, straight from Square's price_money. Needed because the
    # gateway's Money schema requires a currency alongside the amount;
    # the /v1 contract never carried one.
    currency: Mapped[str | None] = mapped_column(Text)
    pricing_type: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    item: Mapped[CatalogItem] = relationship(back_populates="variations")
    location_prices: Mapped[list["CatalogVariationLocationPrice"]] = relationship(
        back_populates="variation", cascade="all, delete-orphan", lazy="raise"
    )


class CatalogVariationLocationPrice(Base):
    """Per-location price override (Square's `location_overrides`).

    Absence of a row for a given variation/location means the flat
    `CatalogVariation.price` applies there.
    """

    __tablename__ = "catalog_variation_location_prices"
    __table_args__ = (
        UniqueConstraint("variation_id", "square_location_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    variation_id: Mapped[str] = mapped_column(
        Text, ForeignKey("catalog_variations.id", ondelete="CASCADE"), nullable=False
    )
    square_location_id: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)

    variation: Mapped[CatalogVariation] = relationship(back_populates="location_prices")


class SyncCursor(Base):
    __tablename__ = "sync_cursors"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    latest_time: Mapped[str] = mapped_column(Text, nullable=False)
