from datetime import datetime, timezone
from pydantic import BaseModel
from pydantic_ai import RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TimeSlot, Job, JobStatus, Customer, Business


class AgentDeps(BaseModel):
    db: AsyncSession
    business_id: int
    business: Business
    customer: Customer

    model_config = {"arbitrary_types_allowed": True}


async def check_availability(ctx: RunContext[AgentDeps]) -> str:
    """Check available time slots for the business."""
    result = await ctx.deps.db.execute(
        select(TimeSlot)
        .where(
            TimeSlot.technician_id.in_(
                select(TimeSlot.technician_id).where(
                    TimeSlot.is_available == True
                )
            ),
            TimeSlot.is_available == True,
            TimeSlot.start_time > datetime.now(timezone.utc),
        )
        .order_by(TimeSlot.start_time.asc())
        .limit(5)
    )
    slots = result.scalars().all()

    if not slots:
        return "No available time slots at the moment."

    lines = []
    for slot in slots:
        lines.append(f"Slot {slot.id}: {slot.start_time.strftime('%A %b %d at %I:%M %p')}")

    return "Available slots:\n" + "\n".join(lines)


async def book_job(ctx: RunContext[AgentDeps], slot_id: int, job_type: str) -> str:
    """Book a job for the customer at the given time slot."""
    db = ctx.deps.db

    result = await db.execute(
        select(TimeSlot).where(TimeSlot.id == slot_id, TimeSlot.is_available == True)
    )
    slot = result.scalar_one_or_none()

    if not slot:
        return "That time slot is no longer available. Please choose another."

    job = Job(
        business_id=ctx.deps.business_id,
        customer_id=ctx.deps.customer.id,
        technician_id=slot.technician_id,
        time_slot_id=slot.id,
        job_type=job_type,
        status=JobStatus.confirmed,
    )
    db.add(job)

    slot.is_available = False
    await db.flush()

    return f"Booked! Your {job_type} appointment is confirmed for {slot.start_time.strftime('%A %b %d at %I:%M %p')}. Reply STOP to opt out."


async def reschedule_job(ctx: RunContext[AgentDeps], job_id: int, new_slot_id: int) -> str:
    """Reschedule an existing job to a new time slot."""
    db = ctx.deps.db

    job_result = await db.execute(
        select(Job).where(Job.id == job_id, Job.customer_id == ctx.deps.customer.id)
    )
    job = job_result.scalar_one_or_none()

    if not job:
        return "I couldn't find that appointment."

    slot_result = await db.execute(
        select(TimeSlot).where(TimeSlot.id == new_slot_id, TimeSlot.is_available == True)
    )
    new_slot = slot_result.scalar_one_or_none()

    if not new_slot:
        return "That time slot is not available. Please choose another."

    # Free up old slot
    old_slot_result = await db.execute(select(TimeSlot).where(TimeSlot.id == job.time_slot_id))
    old_slot = old_slot_result.scalar_one_or_none()
    if old_slot:
        old_slot.is_available = True

    job.time_slot_id = new_slot.id
    job.technician_id = new_slot.technician_id
    new_slot.is_available = False
    await db.flush()

    return f"Rescheduled! Your appointment is now set for {new_slot.start_time.strftime('%A %b %d at %I:%M %p')}."


async def cancel_job(ctx: RunContext[AgentDeps], job_id: int) -> str:
    """Cancel an existing job."""
    db = ctx.deps.db

    job_result = await db.execute(
        select(Job).where(Job.id == job_id, Job.customer_id == ctx.deps.customer.id)
    )
    job = job_result.scalar_one_or_none()

    if not job:
        return "I couldn't find that appointment."

    job.status = JobStatus.cancelled

    if job.time_slot_id:
        slot_result = await db.execute(select(TimeSlot).where(TimeSlot.id == job.time_slot_id))
        slot = slot_result.scalar_one_or_none()
        if slot:
            slot.is_available = True

    await db.flush()
    return "Your appointment has been cancelled. Let us know if you'd like to rebook."
