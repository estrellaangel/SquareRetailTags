from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, TIMESTAMP, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from esl.db import Base


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
    pricing_type: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    item: Mapped[CatalogItem] = relationship(back_populates="variations")


class SyncCursor(Base):
    __tablename__ = "sync_cursors"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    latest_time: Mapped[str] = mapped_column(Text, nullable=False)
