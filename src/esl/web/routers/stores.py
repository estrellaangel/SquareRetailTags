import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from esl.catalog.models import Store
from esl.db import get_session
from esl.web.auth import get_current_user

router = APIRouter()


class StoreCreateBody(BaseModel):
    id: str
    name: str
    square_location_id: str


class StoreResponse(BaseModel):
    id: str
    name: str
    square_location_id: str

    model_config = {"from_attributes": True}


class StoreCreateResponse(StoreResponse):
    api_key: str


@router.post("/stores", response_model=StoreCreateResponse)
async def create_store(
    body: StoreCreateBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    store = Store(
        id=body.id,
        name=body.name,
        square_location_id=body.square_location_id,
        api_key=secrets.token_urlsafe(32),
    )
    session.add(store)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(
            status_code=400,
            detail=f"Store {body.id!r} or its square_location_id already exists",
        )
    return StoreCreateResponse.model_validate(store)


@router.get("/stores", response_model=list[StoreResponse])
async def list_stores(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    stores = (await session.execute(select(Store))).scalars().all()
    return [StoreResponse.model_validate(s) for s in stores]
