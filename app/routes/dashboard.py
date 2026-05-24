from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Job, Customer, JobStatus
from app.schemas import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(business_id: int, db: AsyncSession = Depends(get_db)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    jobs_result = await db.execute(
        select(Job).where(
            Job.business_id == business_id,
            Job.start_time >= today_start,
            Job.start_time < today_end,
        )
    )
    jobs = jobs_result.scalars().all()

    customers_result = await db.execute(
        select(func.count(Customer.id)).where(Customer.business_id == business_id)
    )
    total_customers = customers_result.scalar()

    return DashboardSummary(
        total_jobs_today=len(jobs),
        confirmed=sum(1 for j in jobs if j.status == JobStatus.confirmed),
        completed=sum(1 for j in jobs if j.status == JobStatus.completed),
        no_shows=sum(1 for j in jobs if j.status == JobStatus.no_show),
        cancelled=sum(1 for j in jobs if j.status == JobStatus.cancelled),
        total_customers=total_customers or 0,
    )
