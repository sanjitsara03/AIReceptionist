from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Business
from app.schemas import BusinessResponse, BusinessUpdate
from app.auth import get_current_business_id

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("/me", response_model=BusinessResponse)
async def get_my_business(
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Business).where(Business.id == business_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business


@router.patch("/me", response_model=BusinessResponse)
async def update_my_business(
    update: BusinessUpdate,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Business).where(Business.id == business_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Apply only provided fields
    for key, value in update.model_dump(exclude_unset=True).items():
        setattr(business, key, value)

    await db.commit()
    await db.refresh(business)
    return business
