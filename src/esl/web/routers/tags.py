import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from esl.catalog.models import CatalogVariation, Store
from esl.catalog.pricing import resolve_price
from esl.db import get_session
from esl.tags.commands import enqueue_for_tag, enqueue_locate
from esl.tags.hashing import hash_projection
from esl.tags.models import LabelTelemetry, Tag
from esl.tags.signal import battery_volts, classify
from esl.tags.projection import UNASSIGNED, build_projection
from esl.web.auth import get_current_user

router = APIRouter()

# Security scheme, not a bare Header, so /docs can send it (see central.py).
_store_key = APIKeyHeader(
    name="X-Store-Key",
    auto_error=False,
    scheme_name="StoreKey",
    description="Per-store key for the legacy /v1 gateway routes.",
)


class TagResponse(BaseModel):
    id: str
    store_id: str
    variation_id: str | None = None
    name: str | None = None
    variation_name: str | None = None
    sku: str | None = None
    price: int | None = None
    pricing_type: str | None = None
    content_hash: str | None = None
    last_pushed_at: datetime | None = None
    last_confirmed_at: datetime | None = None
    battery_pct: int | None = None
    signal: str = "never_heard"
    rf_power: int | None = None
    last_seen_at: datetime | None = None
    battery_volts: float | None = None
    low_battery: bool | None = None

    model_config = {"from_attributes": True}


class TagListResponse(BaseModel):
    tags: list[TagResponse]


class AssignBody(BaseModel):
    store_id: str
    variation_id: str | None = None


class LocateBody(BaseModel):
    seconds: int | None = None

    @field_validator("seconds")
    @classmethod
    def seconds_in_range(cls, v: int | None) -> int | None:
        # The gateway's own cap is 300s, but its protocol field allows the
        # full 1..65535 range — mirror the protocol here and let the
        # gateway apply its configured maximum.
        if v is not None and not (1 <= v <= 65535):
            raise ValueError("seconds must be between 1 and 65535")
        return v


class LocateAccepted(BaseModel):
    update_id: str
    tag_id: str
    seconds: int | None = None


class ConfirmBody(BaseModel):
    content_hash: str
    battery_pct: int | None = None

    @field_validator("battery_pct")
    @classmethod
    def battery_in_range(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("battery_pct must be 0–100")
        return v


_TAG_ID_RE = re.compile(r"^[0-9A-F]{12}$")


def _normalize_tag_id(tag_id: str) -> str:
    """Uppercase and validate at the API boundary.

    12 hex characters is the real ESL hardware id length (confirmed
    against api/westgate-store-service.yaml). Rejecting here keeps ids
    the gateway's hardware would refuse as InvalidTagId from ever
    reaching the database.
    """
    normalized = tag_id.upper()
    if not _TAG_ID_RE.match(normalized):
        raise HTTPException(
            status_code=400,
            detail=f"Tag id must be 12 hexadecimal characters, got {tag_id!r}",
        )
    return normalized


async def get_current_store(
    session: AsyncSession = Depends(get_session),
    x_store_key: str | None = Security(_store_key),
) -> Store:
    if not x_store_key:
        raise HTTPException(status_code=401, detail="Missing X-Store-Key header")
    store = (
        await session.execute(select(Store).where(Store.api_key == x_store_key))
    ).scalar_one_or_none()
    if store is None:
        raise HTTPException(status_code=401, detail="Invalid X-Store-Key")
    return store


def _tag_to_response(
    tag: Tag, telemetry: LabelTelemetry | None = None
) -> TagResponse:
    if tag.variation is not None:
        price = resolve_price(tag.variation, tag.store.square_location_id)
        proj = build_projection(tag.variation.item, tag.variation, price)
    else:
        proj = UNASSIGNED

    return TagResponse(
        id=tag.id,
        store_id=tag.store_id,
        variation_id=tag.variation_id,
        content_hash=tag.content_hash,
        last_pushed_at=tag.last_pushed_at,
        last_confirmed_at=tag.last_confirmed_at,
        battery_pct=tag.battery_pct,
        name=proj["name"],
        variation_name=proj["variation_name"],
        sku=proj["sku"],
        price=proj["price"],
        pricing_type=proj["pricing_type"],
        signal=classify(telemetry),
        rf_power=telemetry.rf_power if telemetry else None,
        last_seen_at=telemetry.last_seen_at if telemetry else None,
        battery_volts=battery_volts(telemetry.battery) if telemetry else None,
        low_battery=telemetry.low_battery if telemetry else None,
    )


async def _telemetry_for(session: AsyncSession, tags: list[Tag]) -> dict:
    """Latest telemetry for a set of tags, keyed by (store_id, tag_id).

    Fetched in one query rather than per tag — the tags table is the
    dashboard's busiest view and polls every 5 seconds.
    """
    if not tags:
        return {}
    keys = {(t.store_id, t.id) for t in tags}
    rows = (
        await session.execute(
            select(LabelTelemetry).where(
                LabelTelemetry.tag_id.in_({t.id for t in tags})
            )
        )
    ).scalars().all()
    return {(r.store_id, r.tag_id): r for r in rows if (r.store_id, r.tag_id) in keys}


_TAG_OPTIONS = [
    selectinload(Tag.variation).selectinload(CatalogVariation.item),
    selectinload(Tag.variation).selectinload(CatalogVariation.location_prices),
    selectinload(Tag.store),
]


@router.get("/tags", response_model=TagListResponse)
async def list_tags(
    session: AsyncSession = Depends(get_session),
    store: Store = Depends(get_current_store),
):
    tags = (
        await session.execute(
            select(Tag).where(Tag.store_id == store.id).options(*_TAG_OPTIONS)
        )
    ).scalars().all()
    tele = await _telemetry_for(session, list(tags))
    return TagListResponse(
        tags=[_tag_to_response(t, tele.get((t.store_id, t.id))) for t in tags]
    )


@router.get("/admin/tags", response_model=TagListResponse)
async def list_tags_admin(
    store_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Cross-store listing for the admin dashboard, gated by Auth0 login.

    Unlike GET /tags (the gateway's per-store poll, gated by X-Store-Key),
    this has no store-key concept — the dashboard isn't a gateway and has
    no key to send; it authenticates the human instead. Optional store_id
    narrows to one store.
    """
    query = select(Tag).options(*_TAG_OPTIONS)
    if store_id is not None:
        query = query.where(Tag.store_id == store_id)
    tags = (await session.execute(query)).scalars().all()
    tele = await _telemetry_for(session, list(tags))
    return TagListResponse(
        tags=[_tag_to_response(t, tele.get((t.store_id, t.id))) for t in tags]
    )


@router.get("/tags/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: str,
    session: AsyncSession = Depends(get_session),
    store: Store = Depends(get_current_store),
):
    tag_id = _normalize_tag_id(tag_id)
    tag = await session.get(Tag, tag_id, options=_TAG_OPTIONS)
    if tag is None or tag.store_id != store.id:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")
    telemetry = await session.get(LabelTelemetry, (tag.store_id, tag.id))
    return _tag_to_response(tag, telemetry)


@router.put("/tags/{tag_id}", response_model=TagResponse)
async def assign_tag(
    tag_id: str,
    body: AssignBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    tag_id = _normalize_tag_id(tag_id)

    store = await session.get(Store, body.store_id)
    if store is None:
        raise HTTPException(status_code=404, detail=f"Store {body.store_id} not found")

    variation = None
    if body.variation_id is not None:
        variation = await session.get(
            CatalogVariation, body.variation_id,
            options=[
                selectinload(CatalogVariation.item),
                selectinload(CatalogVariation.location_prices),
            ],
        )
        if variation is None:
            raise HTTPException(status_code=404, detail=f"Variation {body.variation_id} not found")

    tag = await session.get(Tag, tag_id, options=_TAG_OPTIONS)
    if tag is None:
        tag = Tag(id=tag_id, store_id=body.store_id)
        session.add(tag)
    elif tag.store_id != body.store_id:
        raise HTTPException(
            status_code=400,
            detail=f"Tag {tag_id} belongs to store {tag.store_id!r}, not {body.store_id!r}",
        )

    tag.variation_id = body.variation_id

    if variation is not None:
        price = resolve_price(variation, store.square_location_id)
        proj = build_projection(variation.item, variation, price)
        tag.content_hash = hash_projection(proj)
    else:
        # Null, not a hash of the empty projection: the contract defines
        # content_hash == null as "unassigned", and that is the only signal
        # the gateway has to show its unassigned screen instead of trying to
        # render a product with no name and no price.
        proj = None
        tag.content_hash = None

    # Queue the work for the gateway's own contract. The tag must be
    # flushed first: label_commands.tag_id is a foreign key, and a brand
    # new tag has not hit the database yet.
    await session.flush()
    await enqueue_for_tag(
        session, tag, proj, currency=(variation.currency or "USD") if variation else "USD"
    )

    await session.commit()

    # Reload with eager options so _tag_to_response can access variation/store.
    # populate_existing=True is required here: the tag object is already in
    # the session's identity map (client-assigned PK, added above), so a
    # plain session.get() would return it as-is without applying the eager
    # load options, and _tag_to_response would hit lazy="raise".
    tag = await session.get(
        Tag, tag_id, options=_TAG_OPTIONS, populate_existing=True
    )
    return _tag_to_response(tag)


@router.post("/tags/{tag_id}/confirm", status_code=204)
async def confirm_tag(
    tag_id: str,
    body: ConfirmBody,
    session: AsyncSession = Depends(get_session),
    store: Store = Depends(get_current_store),
):
    tag_id = _normalize_tag_id(tag_id)
    tag = await session.get(Tag, tag_id)
    if tag is None or tag.store_id != store.id:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

    tag.last_confirmed_at = datetime.now(timezone.utc)
    if body.battery_pct is not None:
        tag.battery_pct = body.battery_pct

    await session.commit()
    return Response(status_code=204)


@router.post("/tags/{tag_id}/locate", status_code=202, response_model=LocateAccepted)
async def locate_tag(
    tag_id: str,
    body: LocateBody | None = None,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Flash a tag's LED from the dashboard.

    Queues a Locate on the gateway's command queue rather than calling the
    hardware: the store service is LAN-only and unreachable from here, so
    the flash happens on the gateway's next poll.
    """
    tag_id = _normalize_tag_id(tag_id)
    tag = await session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

    seconds = body.seconds if body else None
    command = await enqueue_locate(session, tag, seconds)
    await session.commit()
    return LocateAccepted(
        update_id=command.update_id, tag_id=tag_id, seconds=seconds
    )
