from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, SmallInteger, TIMESTAMP, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from esl.db import Base

if TYPE_CHECKING:
    from esl.catalog.models import CatalogVariation


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    variation_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("catalog_variations.id", ondelete="SET NULL")
    )
    content_hash: Mapped[str | None] = mapped_column(Text)
    last_pushed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    battery_pct: Mapped[int | None] = mapped_column(SmallInteger)

    variation: Mapped[CatalogVariation | None] = relationship(
        "CatalogVariation", lazy="raise"
    )
