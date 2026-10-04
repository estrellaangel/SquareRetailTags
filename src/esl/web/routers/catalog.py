from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from esl.catalog.models import CatalogVariation
from esl.db import get_session
from esl.web.auth import get_current_user

router = APIRouter()


class VariationResponse(BaseModel):
    id: str
    item_id: str
    name: str
    variation_name: str
    sku: str | None = None
    price: int | None = None
    pricing_type: str


class VariationListResponse(BaseModel):
    variations: list[VariationResponse]


@router.get("/catalog/variations", response_model=VariationListResponse)
async def list_variations(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    rows = (
        await session.execute(
            select(CatalogVariation).options(selectinload(CatalogVariation.item))
        )
    ).scalars().all()

    return VariationListResponse(
        variations=[
            VariationResponse(
                id=v.id,
                item_id=v.item_id,
                name=v.item.name,
                variation_name=v.variation_name,
                sku=v.sku,
                price=v.price,
                pricing_type=v.pricing_type,
            )
            for v in rows
        ]
    )
