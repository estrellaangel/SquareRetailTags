"""The store gateway's contract — api/central-esl-api.yaml.

Mounted at the app root (no /v1 prefix) because the gateway's paths are
absolute: /api/label-updates/pending, /api/label-updates/status,
/api/labels/telemetry.

Auth is the same per-store key as the /v1 gateway routes, but the gateway
sends it as X-Api-Key and also names the store in the payload — so every
handler checks the two agree and returns 403 when they don't. Without that
check, any valid key could read or write any store's data.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from esl.catalog.models import Store
from esl.db import get_session
from esl.tags.commands import pending_for_store, serialize_command
from esl.tags.models import AccessPointTelemetry, LabelCommand, LabelTelemetry, Tag

router = APIRouter(tags=["gateway"])

# Declared as a security scheme rather than a bare Header so it appears
# in the generated OpenAPI — that's what puts an Authorize button on
# /docs and lets the page actually send the key.
_api_key = APIKeyHeader(
    name="X-Api-Key",
    auto_error=False,
    # Explicit scheme_name: FastAPI otherwise names every APIKeyHeader
    # after its class, so this and X-Store-Key would collide into one
    # scheme and /docs would send the wrong header for one of them.
    scheme_name="StoreApiKey",
    description="Per-store key, issued once when the store was created.",
)


# ── Auth ────────────────────────────────────────────────────────────────


async def get_api_key_store(
    session: AsyncSession = Depends(get_session),
    x_api_key: str | None = Security(_api_key),
) -> Store:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-Api-Key header")
    store = (
        await session.execute(select(Store).where(Store.api_key == x_api_key))
    ).scalar_one_or_none()
    if store is None:
        raise HTTPException(status_code=401, detail="Invalid X-Api-Key")
    return store


def _authorize_store(store: Store, requested_store_id: str) -> None:
    if store.id != requested_store_id:
        raise HTTPException(
            status_code=403,
            detail=f"API key is not authorized for store {requested_store_id!r}",
        )


# ── Request models ──────────────────────────────────────────────────────


class Diagnostics(BaseModel):
    rfPower: int | None = None
    battery: int | None = None
    temperature: int | None = None
    statusByte: int | None = None
    lowBattery: bool | None = None


class StatusReport(BaseModel):
    updateId: str
    tagId: str
    version: int | None = None
    action: str
    status: str
    statusAt: datetime
    # The gateway's spec says minimum 1, but its implementation sends 0
    # for the first "Accepted" report — queued, not yet attempted. One
    # out-of-range entry would reject the whole batch, which livelocks
    # the gateway: it retries forever and the command never leaves
    # Pending. Accept 0 rather than hold the contract over the hardware.
    attempt: int = Field(ge=0)
    apId: str | None = None
    failureCode: str | None = None
    failureMessage: str | None = None
    retryable: bool | None = None
    diagnostics: Diagnostics | None = None


class StatusBatch(BaseModel):
    storeId: str
    reports: list[StatusReport]


class LabelTelemetryIn(BaseModel):
    tagId: str
    firstSeenAt: datetime | None = None
    lastSeenAt: datetime | None = None
    lastSeenApId: str | None = None
    rfPower: int | None = None
    battery: int | None = None
    lowBattery: bool | None = None
    temperature: int | None = None
    statusByte: int | None = None
    firmwareVersion: int | None = None
    type: int | None = None
    size: int | None = None
    color: int | None = None
    factory: int | None = None
    lastSuccessApId: str | None = None
    lastSuccessAt: datetime | None = None
    lastResultAt: datetime | None = None
    lastResultSuccess: bool | None = None


class AccessPointTelemetryIn(BaseModel):
    apId: str
    connected: bool
    stale: bool
    connectedAt: datetime | None = None
    disconnectedAt: datetime | None = None
    lastHeartbeatAt: datetime | None = None
    heartbeatIntervalSeconds: int | None = None
    apVersion: str | None = None
    ip: str | None = None
    waitCount: int | None = None
    sendCount: int | None = None


class AcceptedCountResponse(BaseModel):
    """How many reports were acknowledged — not how many rows changed.

    The gateway clears its outbox on this number and cannot tell which
    entries a partial count referred to, so it always equals the number of
    reports submitted in an accepted batch.
    """

    acceptedCount: int = Field(ge=0)


class PendingLabelUpdatesResponse(BaseModel):
    updates: list[dict]
    hasMore: bool


class TelemetryReport(BaseModel):
    storeId: str
    reportedAt: datetime
    full: bool
    labels: list[LabelTelemetryIn] = []
    accessPoints: list[AccessPointTelemetryIn] = []


# ── 1. Poll for work ────────────────────────────────────────────────────


@router.get("/api/label-updates/pending", response_model=PendingLabelUpdatesResponse)
async def get_pending_label_updates(
    storeId: str,
    limit: int = Query(default=200, ge=1),
    session: AsyncSession = Depends(get_session),
    store: Store = Depends(get_api_key_store),
):
    _authorize_store(store, storeId)
    commands, has_more = await pending_for_store(session, storeId, limit)
    return {
        "updates": [serialize_command(c) for c in commands],
        "hasMore": has_more,
    }


# ── 2. Report status ────────────────────────────────────────────────────


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.post("/api/label-updates/status", response_model=AcceptedCountResponse)
async def report_label_update_statuses(
    batch: StatusBatch,
    session: AsyncSession = Depends(get_session),
    store: Store = Depends(get_api_key_store),
):
    """Acknowledge a batch of status reports, all or nothing.

    `acceptedCount` is the number of reports *acknowledged*, not the number
    of rows changed. The gateway clears its outbox on this number, and it
    cannot tell which of 62 reports a count of 1 referred to — so a
    duplicate or stale report is an acknowledged no-op, not a rejection.
    Only a batch that fails validation is refused, and then nothing in it
    is applied.
    """
    _authorize_store(store, batch.storeId)

    # ── 1. Validate the whole batch before mutating anything ────────────
    commands: dict[str, LabelCommand | None] = {}
    for report in batch.reports:
        if report.updateId not in commands:
            commands[report.updateId] = await session.get(
                LabelCommand, report.updateId
            )

    foreign = sorted(
        uid
        for uid, command in commands.items()
        if command is not None and command.store_id != store.id
    )
    if foreign:
        # A real authorization failure, so the batch is refused whole and
        # no report in it has been applied — nothing has been written yet.
        raise HTTPException(
            status_code=403,
            detail=(
                "Batch rejected: these updateIds belong to another store: "
                + ", ".join(foreign)
            ),
        )

    # ── 2. Apply the ones that carry newer state ────────────────────────
    # Within one batch the array is ordered oldest-first, and the gateway
    # stamps every report in a batch with the same statusAt — so for equal
    # timestamps, later array position wins. Across batches the rule stays
    # strictly newer-than, as the contract requires.
    applied_in_batch: set[str] = set()

    for report in batch.reports:
        command = commands[report.updateId]
        if command is None:
            # The command no longer exists here — superseded and cleaned
            # up, most likely. The gateway is still holding the report, so
            # acknowledge it rather than making it retry forever.
            continue

        reported_at = _aware(report.statusAt)
        stored_at = _aware(command.status_at) if command.status_at else None
        if stored_at is not None:
            same_batch_tie = (
                report.updateId in applied_in_batch and reported_at == stored_at
            )
            if reported_at < stored_at or (reported_at == stored_at and not same_batch_tie):
                # Duplicate or stale: a safe no-op, still acknowledged.
                continue

        command.status = report.status
        command.status_at = reported_at
        command.attempt = report.attempt
        command.ap_id = report.apId
        command.failure_code = report.failureCode
        command.failure_message = report.failureMessage
        command.retryable = report.retryable
        command.diagnostics = (
            report.diagnostics.model_dump(exclude_none=True)
            if report.diagnostics
            else None
        )
        applied_in_batch.add(report.updateId)

        # A Succeeded Update or Unassign is the label confirming what it
        # displays, which is exactly what the dashboard's "last confirmed"
        # column means. battery_pct is deliberately left alone: the gateway
        # reports raw tenths of a volt and no percentage curve is agreed.
        if report.status == "Succeeded":
            tag = await session.get(Tag, command.tag_id)
            if tag is not None:
                tag.last_confirmed_at = reported_at
                tag.last_pushed_at = tag.last_pushed_at or reported_at

    # ── 3. Commit, then acknowledge every report in the batch ──────────
    await session.commit()
    return AcceptedCountResponse(acceptedCount=len(batch.reports))


# ── 3. Telemetry ────────────────────────────────────────────────────────


@router.post("/api/labels/telemetry", response_model=AcceptedCountResponse)
async def report_label_telemetry(
    report: TelemetryReport,
    session: AsyncSession = Depends(get_session),
    store: Store = Depends(get_api_key_store),
):
    _authorize_store(store, report.storeId)
    reported_at = _aware(report.reportedAt)
    accepted = 0

    for label in report.labels:
        tag_id = label.tagId.upper()
        existing = await session.get(LabelTelemetry, (store.id, tag_id))
        incoming_seen = _aware(label.lastSeenAt) if label.lastSeenAt else None

        if existing is not None and existing.last_seen_at is not None:
            # Snapshot, not an event: older or equal data must not overwrite
            # newer state, since snapshots can arrive out of order.
            if incoming_seen is None or incoming_seen <= _aware(existing.last_seen_at):
                continue

        values = {
            "store_id": store.id,
            "tag_id": tag_id,
            "first_seen_at": label.firstSeenAt,
            "last_seen_at": label.lastSeenAt,
            "last_seen_ap_id": label.lastSeenApId,
            "rf_power": label.rfPower,
            "battery": label.battery,
            "low_battery": label.lowBattery,
            "temperature": label.temperature,
            "status_byte": label.statusByte,
            "firmware_version": label.firmwareVersion,
            "screen_type": label.type,
            "size": label.size,
            "color": label.color,
            "factory": label.factory,
            "last_success_ap_id": label.lastSuccessApId,
            "last_success_at": label.lastSuccessAt,
            "last_result_at": label.lastResultAt,
            "last_result_success": label.lastResultSuccess,
            "reported_at": reported_at,
        }
        await session.execute(
            insert(LabelTelemetry)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["store_id", "tag_id"],
                set_={k: v for k, v in values.items() if k not in ("store_id", "tag_id")},
            )
        )
        accepted += 1

    for ap in report.accessPoints:
        values = {
            "store_id": store.id,
            "ap_id": ap.apId,
            "connected": ap.connected,
            "stale": ap.stale,
            "connected_at": ap.connectedAt,
            "disconnected_at": ap.disconnectedAt,
            "last_heartbeat_at": ap.lastHeartbeatAt,
            "heartbeat_interval_seconds": ap.heartbeatIntervalSeconds,
            "ap_version": ap.apVersion,
            "ip": ap.ip,
            "wait_count": ap.waitCount,
            "send_count": ap.sendCount,
            "reported_at": reported_at,
        }
        await session.execute(
            insert(AccessPointTelemetry)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["store_id", "ap_id"],
                set_={k: v for k, v in values.items() if k not in ("store_id", "ap_id")},
            )
        )
        accepted += 1

    await session.commit()
    return {"acceptedCount": accepted}
