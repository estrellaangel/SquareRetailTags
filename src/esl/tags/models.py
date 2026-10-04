from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    TIMESTAMP,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from esl.db import Base

if TYPE_CHECKING:
    from esl.catalog.models import CatalogVariation, Store


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    store_id: Mapped[str] = mapped_column(
        Text, ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    variation_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("catalog_variations.id", ondelete="SET NULL")
    )
    content_hash: Mapped[str | None] = mapped_column(Text)
    last_pushed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    battery_pct: Mapped[int | None] = mapped_column(SmallInteger)

    # Strictly increasing per tag, bumped whenever the projection changes.
    # The gateway's version ladder decides which of two commands for the
    # same label wins; content_hash detects change but cannot order it.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    variation: Mapped[CatalogVariation | None] = relationship(
        "CatalogVariation", lazy="raise"
    )
    store: Mapped[Store] = relationship("Store", lazy="raise")


class LabelCommand(Base):
    """One unit of work handed to a store's gateway.

    The gateway polls these oldest-first and reports back by `update_id`,
    which is the idempotency key — repeated delivery is expected and safe.
    """

    __tablename__ = "label_commands"
    __table_args__ = (
        Index("label_commands_store_status_created", "store_id", "status", "created_at"),
        Index("label_commands_tag_id", "tag_id"),
    )

    update_id: Mapped[str] = mapped_column(Text, primary_key=True)
    store_id: Mapped[str] = mapped_column(
        Text, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int | None] = mapped_column(Integer)
    product_id: Mapped[str | None] = mapped_column(Text)
    display: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    seconds: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    # Set from the gateway's status reports.
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    attempt: Mapped[int | None] = mapped_column(Integer)
    ap_id: Mapped[str | None] = mapped_column(Text)
    failure_code: Mapped[str | None] = mapped_column(Text)
    failure_message: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[bool | None] = mapped_column(Boolean)
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class LabelTelemetry(Base):
    """Latest telemetry snapshot per label, as reported by its gateway.

    Snapshots, not events: a report is applied only when its `last_seen_at`
    is newer than what is stored.
    """

    __tablename__ = "label_telemetry"

    store_id: Mapped[str] = mapped_column(
        Text, ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(Text, primary_key=True)

    first_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_seen_ap_id: Mapped[str | None] = mapped_column(Text)
    rf_power: Mapped[int | None] = mapped_column(Integer)
    # Raw byte, read as tenths of a volt — NOT a percentage. Deliberately
    # kept in the units the hardware reports; converting to a percentage
    # needs a discharge curve nobody has agreed on yet.
    battery: Mapped[int | None] = mapped_column(Integer)
    low_battery: Mapped[bool | None] = mapped_column(Boolean)
    temperature: Mapped[int | None] = mapped_column(Integer)
    status_byte: Mapped[int | None] = mapped_column(Integer)
    firmware_version: Mapped[int | None] = mapped_column(Integer)
    screen_type: Mapped[int | None] = mapped_column(Integer)
    size: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[int | None] = mapped_column(Integer)
    factory: Mapped[int | None] = mapped_column(Integer)
    last_success_ap_id: Mapped[str | None] = mapped_column(Text)
    last_success_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_result_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_result_success: Mapped[bool | None] = mapped_column(Boolean)
    reported_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class AccessPointTelemetry(Base):
    """Latest state of each access point, per store."""

    __tablename__ = "access_point_telemetry"

    store_id: Mapped[str] = mapped_column(
        Text, ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True
    )
    ap_id: Mapped[str] = mapped_column(Text, primary_key=True)

    connected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    heartbeat_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    ap_version: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(Text)
    wait_count: Mapped[int | None] = mapped_column(Integer)
    send_count: Mapped[int | None] = mapped_column(Integer)
    reported_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
