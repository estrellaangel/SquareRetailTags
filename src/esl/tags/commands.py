"""The command queue the store gateway polls.

The /v1 contract publishes *desired state* and lets the gateway diff it by
content_hash. The real Pi gateway consumes a different model
(api/central-esl-api.yaml): an ordered queue of commands, each with an
idempotency key and a per-tag version. This module owns that queue —
creating commands when a tag's projection changes, and keeping the version
ladder strictly increasing per tag.

Money is still an integer in the smallest currency unit everywhere inside
this service; `money_amount` renders it as a decimal string only at the
boundary, because the gateway's Money schema requires a string.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from esl.tags.models import LabelCommand, Tag
from esl.tags.projection import Projection

ACTION_UPDATE = "Update"
ACTION_UNASSIGN = "Unassign"
ACTION_LOCATE = "Locate"

STATUS_PENDING = "Pending"
STATUS_ACCEPTED = "Accepted"
STATUS_SUCCEEDED = "Succeeded"
STATUS_FAILED = "Failed"
STATUS_SUPERSEDED = "Superseded"

FINAL_STATUSES = frozenset({STATUS_SUCCEEDED, STATUS_FAILED, STATUS_SUPERSEDED})

# ISO 4217 exponents for the currencies we can actually see from Square.
# Anything not listed uses 2, which covers the overwhelming majority.
_ZERO_DECIMAL = frozenset({"JPY", "KRW", "VND", "CLP", "ISK", "XAF", "XOF"})
_THREE_DECIMAL = frozenset({"BHD", "IQD", "JOD", "KWD", "OMR", "TND"})


def currency_exponent(currency: str) -> int:
    if currency in _ZERO_DECIMAL:
        return 0
    if currency in _THREE_DECIMAL:
        return 3
    return 2


def money_amount(minor_units: int, currency: str) -> str:
    """Render integer minor units as the decimal string the gateway wants.

    Never float: the conversion is done on the integer with string
    formatting, so 1999 USD is exactly "19.99" and 11100 is "111.00".
    """
    exponent = currency_exponent(currency)
    if exponent == 0:
        return str(minor_units)
    sign = "-" if minor_units < 0 else ""
    digits = str(abs(minor_units)).rjust(exponent + 1, "0")
    return f"{sign}{digits[:-exponent]}.{digits[-exponent:]}"


def build_display(projection: Projection, currency: str) -> dict:
    """ProductDisplay from a store-resolved projection.

    `variationName` is passed through exactly as Square has it, including
    "Regular" — the gateway's spec says it decides what to hide. An empty
    variation name becomes null rather than an empty string, since the
    gateway's schema models "no variation" as null.
    """
    price = projection["price"]
    if price is None:
        raise ValueError(
            "cannot build a display for a variable-priced variation: "
            "the gateway's ProductDisplay requires a price"
        )
    return {
        "itemName": projection["name"],
        "variationName": projection["variation_name"] or None,
        "price": {"amount": money_amount(price, currency), "currency": currency},
        "sku": projection["sku"],
        "category": None,
        "description": None,
    }


async def _supersede_pending(session: AsyncSession, tag_id: str) -> None:
    """Retire still-pending work for a tag before queueing newer work.

    Without this the gateway would render an out-of-date screen on its way
    to the current one — an extra write to an e-ink label for no benefit.
    """
    await session.execute(
        update(LabelCommand)
        .where(LabelCommand.tag_id == tag_id, LabelCommand.status == STATUS_PENDING)
        .values(status=STATUS_SUPERSEDED, status_at=datetime.now(timezone.utc))
    )


async def enqueue_for_tag(
    session: AsyncSession,
    tag: Tag,
    projection: Projection | None,
    currency: str = "USD",
) -> LabelCommand | None:
    """Queue an Update (or Unassign) for a tag whose content just changed.

    `projection` is None when the tag has no variation assigned. Returns the
    new command, or None when there is nothing renderable to send — a
    variable-priced variation has no price and the gateway cannot render a
    product without one.
    """
    await _supersede_pending(session, tag.id)

    tag.version = (tag.version or 0) + 1

    if projection is None:
        command = LabelCommand(
            update_id=str(uuid.uuid4()),
            store_id=tag.store_id,
            tag_id=tag.id,
            action=ACTION_UNASSIGN,
            version=tag.version,
            created_at=datetime.now(timezone.utc),
            status=STATUS_PENDING,
        )
        session.add(command)
        return command

    if projection["price"] is None:
        # VARIABLE_PRICING: the gateway's Display requires a price, so there
        # is no valid command to send. The tag keeps its bumped version so a
        # later fixed price still wins the ladder.
        return None

    command = LabelCommand(
        update_id=str(uuid.uuid4()),
        store_id=tag.store_id,
        tag_id=tag.id,
        action=ACTION_UPDATE,
        version=tag.version,
        product_id=tag.variation_id,
        display=build_display(projection, currency),
        created_at=datetime.now(timezone.utc),
        status=STATUS_PENDING,
    )
    session.add(command)
    return command


async def enqueue_locate(
    session: AsyncSession, tag: Tag, seconds: int | None = None
) -> LabelCommand:
    """Queue an LED flash. Locate sits outside the version ladder."""
    command = LabelCommand(
        update_id=str(uuid.uuid4()),
        store_id=tag.store_id,
        tag_id=tag.id,
        action=ACTION_LOCATE,
        version=None,
        seconds=seconds,
        created_at=datetime.now(timezone.utc),
        status=STATUS_PENDING,
    )
    session.add(command)
    return command


def serialize_command(command: LabelCommand) -> dict:
    """One LabelCommand in the shape the gateway's discriminator expects."""
    body = {
        "updateId": command.update_id,
        "storeId": command.store_id,
        "tagId": command.tag_id,
        "action": command.action,
        "createdAt": _iso(command.created_at),
    }
    if command.action == ACTION_LOCATE:
        body["version"] = None
        body["seconds"] = command.seconds if command.seconds is not None else 30
        return body

    body["version"] = command.version
    if command.action == ACTION_UPDATE:
        body["productId"] = command.product_id
        body["display"] = command.display
    return body


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def pending_for_store(
    session: AsyncSession, store_id: str, limit: int
) -> tuple[list[LabelCommand], bool]:
    """Oldest-first pending commands, plus whether more remain.

    Fetches one extra row to answer hasMore without a second count query.
    """
    rows = (
        await session.execute(
            select(LabelCommand)
            .where(
                LabelCommand.store_id == store_id,
                LabelCommand.status == STATUS_PENDING,
            )
            .order_by(LabelCommand.created_at.asc(), LabelCommand.update_id.asc())
            .limit(limit + 1)
        )
    ).scalars().all()
    return list(rows[:limit]), len(rows) > limit
