from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Job, Customer, JobStatus, TimeSlot, Conversation, MessageDirection
from app.schemas import DashboardSummary, FeedItem
from app.auth import get_current_business_id

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _today_bounds():
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    today_start, today_end = _today_bounds()

    jobs_result = await db.execute(
        select(Job)
        .join(TimeSlot, Job.time_slot_id == TimeSlot.id)
        .where(
            Job.business_id == business_id,
            TimeSlot.start_time >= today_start,
            TimeSlot.start_time < today_end,
        )
    )
    jobs = jobs_result.scalars().all()

    conv_count_result = await db.execute(
        select(func.count(Conversation.id))
        .join(Customer, Conversation.customer_id == Customer.id)
        .where(
            Customer.business_id == business_id,
            Conversation.created_at >= today_start,
            Conversation.created_at < today_end,
        )
    )
    conversations_today = conv_count_result.scalar() or 0

    cust_result = await db.execute(
        select(func.count(Customer.id)).where(Customer.business_id == business_id)
    )
    total_customers = cust_result.scalar() or 0

    ai_jobs = [j for j in jobs if j.source == "ai"]
    human_jobs = [j for j in jobs if j.source == "human"]

    return DashboardSummary(
        total_jobs_today=len(jobs),
        in_progress=sum(1 for j in jobs if j.status == JobStatus.in_progress),
        confirmed=sum(1 for j in jobs if j.status == JobStatus.confirmed),
        pending=sum(1 for j in jobs if j.status == JobStatus.pending),
        completed=sum(1 for j in jobs if j.status == JobStatus.completed),
        no_shows=sum(1 for j in jobs if j.status == JobStatus.no_show),
        cancelled=sum(1 for j in jobs if j.status == JobStatus.cancelled),
        ai_booked_today=len(ai_jobs),
        ai_booked_revenue=sum(j.estimate or 0 for j in ai_jobs),
        human_booked_today=len(human_jobs),
        conversations_today=conversations_today,
        total_customers=total_customers,
    )


@router.get("/feed", response_model=list[FeedItem])
async def get_feed(
    business_id: int = Depends(get_current_business_id),
    limit: int = 15,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .join(Customer, Conversation.customer_id == Customer.id)
        .where(Customer.business_id == business_id)
        .options(
            selectinload(Conversation.customer),
            selectinload(Conversation.messages),
        )
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    convs = result.scalars().all()

    items = []
    for conv in convs:
        outbound = [m for m in conv.messages if m.direction == MessageDirection.outbound]

        kind = "info"
        verb = "called in" if conv.channel == "voice" else "texted in"

        for m in outbound:
            b = m.body.lower()
            if "rescheduled" in b:
                kind = "reschedule"
                verb = "rescheduled"
                break
            elif "cancelled" in b or "canceled" in b:
                kind = "cancelled"
                verb = "cancelled"
                break
            elif "booked" in b or "scheduled" in b:
                kind = "booked"
                verb = "booked an appointment"
                break

        items.append(FeedItem(
            id=conv.id,
            kind=kind,
            customer_name=conv.customer.name,
            verb=verb,
            channel=conv.channel,
            when_iso=conv.updated_at,
        ))

    return items
