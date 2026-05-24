from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Job, JobStatus
from app.schemas import JobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
async def list_jobs(business_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job)
        .where(Job.business_id == business_id)
        .options(selectinload(Job.customer), selectinload(Job.technician))
        .order_by(Job.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, business_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id, Job.business_id == business_id)
        .options(selectinload(Job.customer), selectinload(Job.technician))
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@router.patch("/{job_id}/status", response_model=JobResponse)
async def update_job_status(
    job_id: int,
    business_id: int,
    status: JobStatus,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id, Job.business_id == business_id)
        .options(selectinload(Job.customer), selectinload(Job.technician))
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = status
    await db.commit()
    await db.refresh(job)

    return job
