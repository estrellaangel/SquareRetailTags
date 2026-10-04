from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from esl.catalog.models import (
    CatalogItem,
    CatalogVariation,
    CatalogVariationLocationPrice,
    SyncCursor,
)
from esl.catalog.pricing import resolve_price
from esl.square.client import get_client
from esl.tags.commands import enqueue_for_tag
from esl.tags.hashing import hash_projection
from esl.tags.models import Tag
from esl.tags.projection import build_projection

CURSOR_ID = "catalog"


async def sync_catalog(session: AsyncSession) -> dict:
    client = get_client()

    row = await session.get(SyncCursor, CURSOR_ID)
    begin_time: str | None = row.latest_time if row else None

    items_upserted = 0
    variations_upserted = 0
    updated_variation_ids: set[str] = set()
    page_cursor: str | None = None
    latest_time: str | None = None

    while True:
        kwargs: dict = {
            "object_types": ["ITEM"],
            "include_related_objects": False,
        }
        if begin_time:
            kwargs["begin_time"] = begin_time
        if page_cursor:
            kwargs["cursor"] = page_cursor

        response = client.catalog.search(**kwargs)

        for obj in response.objects or []:
            if obj.type != "ITEM" or obj.item_data is None:
                continue

            updated_at = _parse_dt(obj.updated_at)

            await session.execute(
                insert(CatalogItem)
                .values(id=obj.id, name=obj.item_data.name, updated_at=updated_at)
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={"name": obj.item_data.name, "updated_at": updated_at},
                )
            )
            items_upserted += 1

            for var in obj.item_data.variations or []:
                if var.item_variation_data is None:
                    continue
                vd = var.item_variation_data
                pricing_type = (vd.pricing_type or "FIXED_PRICING").upper()
                price = vd.price_money.amount if vd.price_money is not None else None
                currency = (
                    vd.price_money.currency if vd.price_money is not None else None
                )
                var_updated_at = _parse_dt(var.updated_at)

                await session.execute(
                    insert(CatalogVariation)
                    .values(
                        id=var.id,
                        item_id=obj.id,
                        variation_name=vd.name or "",
                        sku=vd.sku or None,
                        price=price,
                        currency=currency,
                        pricing_type=pricing_type,
                        updated_at=var_updated_at,
                    )
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            "item_id": obj.id,
                            "variation_name": vd.name or "",
                            "sku": vd.sku or None,
                            "price": price,
                            "currency": currency,
                            "pricing_type": pricing_type,
                            "updated_at": var_updated_at,
                        },
                    )
                )
                updated_variation_ids.add(var.id)
                variations_upserted += 1

                for override in vd.location_overrides or []:
                    if override.location_id is None or override.price_money is None:
                        continue
                    await session.execute(
                        insert(CatalogVariationLocationPrice)
                        .values(
                            variation_id=var.id,
                            square_location_id=override.location_id,
                            price=override.price_money.amount,
                        )
                        .on_conflict_do_update(
                            index_elements=["variation_id", "square_location_id"],
                            set_={"price": override.price_money.amount},
                        )
                    )

        if response.latest_time:
            latest_time = response.latest_time

        if response.cursor:
            page_cursor = response.cursor
        else:
            break

    # Flush catalog writes so the session sees fresh variation data below.
    await session.flush()

    # Recompute content_hash for any tag whose variation was just updated.
    tags_rehashed = 0
    if updated_variation_ids:
        tags = (
            await session.execute(
                select(Tag)
                .where(Tag.variation_id.in_(updated_variation_ids))
                .options(
                    selectinload(Tag.variation).selectinload(CatalogVariation.item),
                    selectinload(Tag.variation).selectinload(
                        CatalogVariation.location_prices
                    ),
                    selectinload(Tag.store),
                )
            )
        ).scalars().all()

        for tag in tags:
            if tag.variation is None:
                continue
            price = resolve_price(tag.variation, tag.store.square_location_id)
            new_hash = hash_projection(
                build_projection(tag.variation.item, tag.variation, price)
            )
            if tag.content_hash != new_hash:
                tag.content_hash = new_hash
                tags_rehashed += 1
                # Same change, expressed in the gateway's own model: a new
                # command on the tag's version ladder. Queued here rather
                # than left for the gateway to discover by diffing.
                await enqueue_for_tag(
                    session,
                    tag,
                    build_projection(tag.variation.item, tag.variation, price),
                    currency=tag.variation.currency or "USD",
                )

    if latest_time:
        await session.execute(
            insert(SyncCursor)
            .values(id=CURSOR_ID, latest_time=latest_time)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"latest_time": latest_time},
            )
        )

    await session.commit()

    return {
        "items_upserted": items_upserted,
        "variations_upserted": variations_upserted,
        "tags_rehashed": tags_rehashed,
        "latest_time": latest_time,
    }


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
