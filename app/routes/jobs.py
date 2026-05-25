from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Job, JobStatus, Customer, TimeSlot, Technician
from app.schemas import JobResponse, JobCreate, JobReschedule
from app.auth import get_current_business_id
from app.events import publish

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _full_job_query():
    """Selectinload chain we need to return a complete JobResponse."""
    return [
        selectinload(Job.customer).selectinload(Customer.jobs),
        selectinload(Job.technician),
        selectinload(Job.time_slot),
    ]


async def _get_scoped_job(db: AsyncSession, job_id: int, business_id: int) -> Job:
    """Fetch a job by id, scoped to the business, with relationships eager-loaded."""
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id, Job.business_id == business_id)
        .options(*_full_job_query())
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    result = await db.execute(
        select(Job)
        .where(Job.business_id == business_id)
        .options(*_full_job_query())
        .order_by(Job.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    return await _get_scoped_job(db, job_id, business_id)


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    payload: JobCreate,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    """Manually book a job (source='human'). Validates customer + slot belong to this business."""
    # Verify the customer is in this business
    cust = await db.execute(
        select(Customer).where(Customer.id == payload.customer_id, Customer.business_id == business_id)
    )
    if not cust.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Customer not found")

    # Verify the slot belongs to this business AND is available
    slot_result = await db.execute(
        select(TimeSlot)
        .join(Technician, TimeSlot.technician_id == Technician.id)
        .where(
            TimeSlot.id == payload.time_slot_id,
            TimeSlot.is_available == True,
            Technician.business_id == business_id,
        )
    )
    slot = slot_result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=400, detail="Time slot is unavailable.")

    job = Job(
        business_id=business_id,
        customer_id=payload.customer_id,
        technician_id=slot.technician_id,
        time_slot_id=slot.id,
        job_type=payload.job_type,
        status=JobStatus.confirmed,
        source="human",
        estimate=payload.estimate,
        notes=payload.notes,
    )
    slot.is_available = False
    db.add(job)
    await db.commit()

    publish(business_id, "job.created", {"job_id": job.id})
    return await _get_scoped_job(db, job.id, business_id)


@router.patch("/{job_id}/status", response_model=JobResponse)
async def update_job_status(
    job_id: int,
    status: JobStatus,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_scoped_job(db, job_id, business_id)
    previous = job.status
    job.status = status

    # If cancelling, free the slot so it can be re-booked
    if status == JobStatus.cancelled and previous != JobStatus.cancelled and job.time_slot:
        job.time_slot.is_available = True

    await db.commit()
    await db.refresh(job)
    publish(business_id, "job.updated", {"job_id": job.id})
    return job


@router.patch("/{job_id}/reschedule", response_model=JobResponse)
async def reschedule_job(
    job_id: int,
    payload: JobReschedule,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_scoped_job(db, job_id, business_id)

    # New slot must belong to this business and be available
    slot_result = await db.execute(
        select(TimeSlot)
        .join(Technician, TimeSlot.technician_id == Technician.id)
        .where(
            TimeSlot.id == payload.new_slot_id,
            TimeSlot.is_available == True,
            Technician.business_id == business_id,
        )
    )
    new_slot = slot_result.scalar_one_or_none()
    if not new_slot:
        raise HTTPException(status_code=400, detail="Selected time slot is unavailable.")

    # Free old slot
    if job.time_slot:
        job.time_slot.is_available = True

    job.time_slot_id = new_slot.id
    job.technician_id = new_slot.technician_id
    new_slot.is_available = False

    # If it was cancelled, picking a new slot re-confirms it
    if job.status == JobStatus.cancelled:
        job.status = JobStatus.confirmed

    await db.commit()
    publish(business_id, "job.updated", {"job_id": job.id})
    return await _get_scoped_job(db, job.id, business_id)
