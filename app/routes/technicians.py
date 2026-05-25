from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Technician
from app.schemas import TechnicianResponse, TechnicianCreate, TechnicianUpdate
from app.auth import get_current_business_id

router = APIRouter(prefix="/technicians", tags=["technicians"])


@router.get("", response_model=list[TechnicianResponse])
async def list_technicians(
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Technician)
        .where(Technician.business_id == business_id)
        .order_by(Technician.name)
    )
    return result.scalars().all()


@router.post("", response_model=TechnicianResponse, status_code=201)
async def create_technician(
    payload: TechnicianCreate,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    tech = Technician(
        business_id=business_id,
        name=payload.name,
        phone=payload.phone,
        active=payload.active,
    )
    db.add(tech)
    await db.commit()
    await db.refresh(tech)
    return tech


@router.patch("/{technician_id}", response_model=TechnicianResponse)
async def update_technician(
    technician_id: int,
    payload: TechnicianUpdate,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Technician).where(
            Technician.id == technician_id,
            Technician.business_id == business_id,
        )
    )
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tech, key, value)

    await db.commit()
    await db.refresh(tech)
    return tech


@router.delete("/{technician_id}", status_code=204)
async def delete_technician(
    technician_id: int,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Technician).where(
            Technician.id == technician_id,
            Technician.business_id == business_id,
        )
    )
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    await db.delete(tech)
    await db.commit()
