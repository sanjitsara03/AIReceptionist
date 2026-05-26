from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import TimeSlot, Technician
from app.schemas import (
    TimeSlotResponse,
    TimeSlotFullResponse,
    TimeSlotCreate,
    TimeSlotBulkCreate,
)
from app.auth import get_current_business_id

router = APIRouter(prefix="/timeslots", tags=["timeslots"])


async def _verify_tech_belongs_to_business(
    db: AsyncSession, technician_id: int, business_id: int
) -> Technician:
    result = await db.execute(
        select(Technician).where(
            Technician.id == technician_id,
            Technician.business_id == business_id,
        )
    )
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
    return tech


# ----------------------------------------------------------------------------
# Read endpoints
# ----------------------------------------------------------------------------

@router.get("/available", response_model=list[TimeSlotResponse])
async def list_available(
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
    days: int = Query(14, ge=1, le=60, description="How many days ahead to look"),
    limit: int = Query(200, ge=1, le=500),
):
    """Open future slots for this business — used by booking forms."""
    now = datetime.now(timezone.utc)
    window = now + timedelta(days=days)

    result = await db.execute(
        select(TimeSlot, Technician.name)
        .join(Technician, TimeSlot.technician_id == Technician.id)
        .where(
            Technician.business_id == business_id,
            TimeSlot.is_available == True,
            TimeSlot.start_time >= now,
            TimeSlot.start_time <= window,
        )
        .order_by(TimeSlot.start_time.asc())
        .limit(limit)
    )

    return [
        TimeSlotResponse(
            id=slot.id,
            technician_id=slot.technician_id,
            technician_name=tech_name,
            start_time=slot.start_time,
            end_time=slot.end_time,
        )
        for slot, tech_name in result.all()
    ]


@router.get("", response_model=list[TimeSlotFullResponse])
async def list_all(
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=120),
    limit: int = Query(500, ge=1, le=2000),
):
    """All upcoming slots for this business (booked or free) — for the availability calendar."""
    now = datetime.now(timezone.utc)
    window = now + timedelta(days=days)

    result = await db.execute(
        select(TimeSlot, Technician.name)
        .join(Technician, TimeSlot.technician_id == Technician.id)
        .where(
            Technician.business_id == business_id,
            TimeSlot.start_time >= now,
            TimeSlot.start_time <= window,
        )
        .order_by(TimeSlot.start_time.asc())
        .limit(limit)
    )

    return [
        TimeSlotFullResponse(
            id=slot.id,
            technician_id=slot.technician_id,
            technician_name=tech_name,
            start_time=slot.start_time,
            end_time=slot.end_time,
            is_available=slot.is_available,
        )
        for slot, tech_name in result.all()
    ]


# ----------------------------------------------------------------------------
# Mutations
# ----------------------------------------------------------------------------

@router.post("", response_model=TimeSlotFullResponse, status_code=201)
async def create_slot(
    payload: TimeSlotCreate,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a single time slot for one of this business's technicians."""
    tech = await _verify_tech_belongs_to_business(db, payload.technician_id, business_id)

    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    slot = TimeSlot(
        technician_id=tech.id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        is_available=True,
    )
    db.add(slot)
    await db.commit()
    await db.refresh(slot)

    return TimeSlotFullResponse(
        id=slot.id,
        technician_id=slot.technician_id,
        technician_name=tech.name,
        start_time=slot.start_time,
        end_time=slot.end_time,
        is_available=slot.is_available,
    )


@router.post("/bulk", response_model=list[TimeSlotFullResponse], status_code=201)
async def create_slots_bulk(
    payload: TimeSlotBulkCreate,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Create recurring slots: for each calendar day between start_date and end_date,
    if that day's weekday is in `weekdays`, create slots from day_start_hour to
    day_end_hour, each of length `slot_minutes`.
    """
    tech = await _verify_tech_belongs_to_business(db, payload.technician_id, business_id)

    if payload.end_date <= payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    if not (0 <= payload.day_start_hour < payload.day_end_hour <= 24):
        raise HTTPException(status_code=400, detail="Invalid day_start_hour / day_end_hour")
    if payload.slot_minutes <= 0 or payload.slot_minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="slot_minutes must be between 1 and 1440")
    if not payload.weekdays or any(d < 0 or d > 6 for d in payload.weekdays):
        raise HTTPException(status_code=400, detail="weekdays must be a non-empty list of 0..6")

    weekdays = set(payload.weekdays)
    slot_delta = timedelta(minutes=payload.slot_minutes)
    created: list[TimeSlot] = []

    # Anchor the weekday + hour math in California time. "Tuesday 9am to 5pm"
    # means PT Tuesday and PT business hours regardless of where the caller
    # or container is. Naive inputs are assumed to be UTC.
    from app.config import BUSINESS_TZ

    def _to_pt(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BUSINESS_TZ)

    day = _to_pt(payload.start_date).replace(hour=0, minute=0, second=0, microsecond=0)
    end_day = _to_pt(payload.end_date).replace(hour=0, minute=0, second=0, microsecond=0)

    # Hard cap so a typo can't fill the DB
    if (end_day - day).days > 90:
        raise HTTPException(status_code=400, detail="Date range too large (max 90 days).")

    while day < end_day:
        if day.weekday() in weekdays:
            # PT wall-clock cursor; converted to UTC before inserting.
            cursor = day.replace(hour=payload.day_start_hour)
            day_close = day.replace(hour=0) + timedelta(hours=payload.day_end_hour)
            while cursor + slot_delta <= day_close:
                slot = TimeSlot(
                    technician_id=tech.id,
                    start_time=cursor.astimezone(timezone.utc),
                    end_time=(cursor + slot_delta).astimezone(timezone.utc),
                    is_available=True,
                )
                db.add(slot)
                created.append(slot)
                cursor += slot_delta
        day += timedelta(days=1)

    await db.commit()
    for s in created:
        await db.refresh(s)

    return [
        TimeSlotFullResponse(
            id=s.id,
            technician_id=s.technician_id,
            technician_name=tech.name,
            start_time=s.start_time,
            end_time=s.end_time,
            is_available=s.is_available,
        )
        for s in created
    ]


@router.delete("/{slot_id}", status_code=204)
async def delete_slot(
    slot_id: int,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a time slot. Only allowed if the slot is still available (not booked)."""
    result = await db.execute(
        select(TimeSlot)
        .join(Technician, TimeSlot.technician_id == Technician.id)
        .where(TimeSlot.id == slot_id, Technician.business_id == business_id)
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    if not slot.is_available:
        raise HTTPException(status_code=409, detail="Cannot delete a booked slot. Cancel the job first.")

    await db.delete(slot)
    await db.commit()
