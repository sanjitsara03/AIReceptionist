from datetime import datetime, timezone
from pydantic import BaseModel
from pydantic_ai import RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import fmt_pt
from app.models import TimeSlot, Job, JobStatus, Customer, Business, Technician
from app.events import publish


# Rough price estimates by job type — used so dashboard revenue isn't always 0.
JOB_ESTIMATES = {
    "drain cleaning": 180,
    "pipe repair": 380,
    "water heater repair": 320,
    "water heater install": 540,
    "leak detection": 220,
    "bathroom plumbing": 380,
    "kitchen sink install": 290,
    "emergency clog": 245,
    "garbage disposal": 195,
    "sewer line inspection": 350,
}


def _estimate_for(job_type: str) -> int | None:
    # Case-insensitive match. Prefer exact, then longest substring match so
    # ambiguous inputs like "water heater" don't randomly pick "repair" vs
    # "install" based on dict iteration order.
    key = job_type.lower().strip()
    if key in JOB_ESTIMATES:
        return JOB_ESTIMATES[key]
    best_known: str | None = None
    for known in JOB_ESTIMATES:
        if known in key or key in known:
            if best_known is None or len(known) > len(best_known):
                best_known = known
    return JOB_ESTIMATES[best_known] if best_known else None


class AgentDeps(BaseModel):
    db: AsyncSession
    business_id: int
    business: Business
    customer: Customer

    model_config = {"arbitrary_types_allowed": True}


async def list_my_appointments(ctx: RunContext[AgentDeps]) -> str:
    # Caller's own upcoming jobs — agent must call this instead of asking for a "job ID".
    db = ctx.deps.db

    active_statuses = [JobStatus.confirmed, JobStatus.pending, JobStatus.in_progress]
    result = await db.execute(
        select(Job, TimeSlot)
        .join(TimeSlot, Job.time_slot_id == TimeSlot.id)
        .where(
            Job.customer_id == ctx.deps.customer.id,
            Job.business_id == ctx.deps.business_id,
            Job.status.in_(active_statuses),
            TimeSlot.start_time >= datetime.now(timezone.utc),
        )
        .order_by(TimeSlot.start_time.asc())
    )
    rows = result.all()

    if not rows:
        return "No upcoming appointments on file for this phone number."

    lines = [
        f"Job {job.id}: {job.job_type} on "
        f"{fmt_pt(slot.start_time, '%A %b %d at %I:%M %p')} (status: {job.status.value})"
        for job, slot in rows
    ]
    return "Your upcoming appointments:\n" + "\n".join(lines)


async def check_availability(ctx: RunContext[AgentDeps]) -> str:
    # Next 5 available slots for THIS business only.
    result = await ctx.deps.db.execute(
        select(TimeSlot)
        .join(Technician, TimeSlot.technician_id == Technician.id)
        .where(
            Technician.business_id == ctx.deps.business_id,
            TimeSlot.is_available == True,
            TimeSlot.start_time > datetime.now(timezone.utc),
        )
        .order_by(TimeSlot.start_time.asc())
        .limit(5)
    )
    slots = result.scalars().all()

    if not slots:
        return "No available time slots at the moment."

    lines = [
        f"Slot {slot.id}: {fmt_pt(slot.start_time, '%A %b %d at %I:%M %p')}"
        for slot in slots
    ]
    return "Available slots:\n" + "\n".join(lines)


async def book_job(ctx: RunContext[AgentDeps], slot_id: int, job_type: str) -> str:
    # Book a job for the caller — slot must belong to THIS business.
    db = ctx.deps.db

    result = await db.execute(
        select(TimeSlot)
        .join(Technician, TimeSlot.technician_id == Technician.id)
        .where(
            TimeSlot.id == slot_id,
            TimeSlot.is_available == True,
            Technician.business_id == ctx.deps.business_id,
        )
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
        source="ai",
        estimate=_estimate_for(job_type),
    )
    db.add(job)
    slot.is_available = False
    await db.flush()

    publish(ctx.deps.business_id, "job.created", {"job_id": job.id})

    return (
        f"Booked! Your {job_type} appointment is confirmed for "
        f"{fmt_pt(slot.start_time, '%A %b %d at %I:%M %p')}. Reply STOP to opt out."
    )


async def reschedule_job(ctx: RunContext[AgentDeps], job_id: int, new_slot_id: int) -> str:
    # Reschedule — job AND new slot must both belong to THIS business.
    db = ctx.deps.db

    job_result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.customer_id == ctx.deps.customer.id,
            Job.business_id == ctx.deps.business_id,
        )
    )
    job = job_result.scalar_one_or_none()

    if not job:
        return "I couldn't find that appointment."

    slot_result = await db.execute(
        select(TimeSlot)
        .join(Technician, TimeSlot.technician_id == Technician.id)
        .where(
            TimeSlot.id == new_slot_id,
            TimeSlot.is_available == True,
            Technician.business_id == ctx.deps.business_id,
        )
    )
    new_slot = slot_result.scalar_one_or_none()

    if not new_slot:
        return "That time slot is not available. Please choose another."

    # Free the previously held slot before claiming the new one.
    if job.time_slot_id:
        old_slot_result = await db.execute(select(TimeSlot).where(TimeSlot.id == job.time_slot_id))
        old_slot = old_slot_result.scalar_one_or_none()
        if old_slot:
            old_slot.is_available = True

    job.time_slot_id = new_slot.id
    job.technician_id = new_slot.technician_id
    new_slot.is_available = False
    await db.flush()

    publish(ctx.deps.business_id, "job.updated", {"job_id": job.id})

    return f"Rescheduled! Your appointment is now set for {fmt_pt(new_slot.start_time, '%A %b %d at %I:%M %p')}."


async def cancel_all_jobs(ctx: RunContext[AgentDeps]) -> str:
    # Cancel every upcoming/active job for THIS customer at THIS business.
    # Use when the caller says "cancel all my appointments", "cancel everything",
    # "wipe my schedule", etc. Prefer cancel_job when they name a specific one.
    db = ctx.deps.db

    active_statuses = [JobStatus.confirmed, JobStatus.pending, JobStatus.in_progress]
    result = await db.execute(
        select(Job, TimeSlot)
        .outerjoin(TimeSlot, Job.time_slot_id == TimeSlot.id)
        .where(
            Job.customer_id == ctx.deps.customer.id,
            Job.business_id == ctx.deps.business_id,
            Job.status.in_(active_statuses),
            TimeSlot.start_time >= datetime.now(timezone.utc),
        )
    )
    rows = result.all()

    if not rows:
        return "No upcoming appointments to cancel."

    cancelled_ids: list[int] = []
    for job, slot in rows:
        job.status = JobStatus.cancelled
        if slot is not None:
            slot.is_available = True
        cancelled_ids.append(job.id)

    await db.flush()
    for jid in cancelled_ids:
        publish(ctx.deps.business_id, "job.updated", {"job_id": jid})

    return f"Cancelled {len(cancelled_ids)} appointment(s) for this caller."


async def cancel_job(ctx: RunContext[AgentDeps], job_id: int) -> str:
    # Cancel — must belong to THIS business.
    db = ctx.deps.db

    job_result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.customer_id == ctx.deps.customer.id,
            Job.business_id == ctx.deps.business_id,
        )
    )
    job = job_result.scalar_one_or_none()

    if not job:
        return "I couldn't find that appointment."

    job.status = JobStatus.cancelled

    # Free the slot so other customers can book it.
    if job.time_slot_id:
        slot_result = await db.execute(select(TimeSlot).where(TimeSlot.id == job.time_slot_id))
        slot = slot_result.scalar_one_or_none()
        if slot:
            slot.is_available = True

    await db.flush()

    publish(ctx.deps.business_id, "job.updated", {"job_id": job.id})

    return "Your appointment has been cancelled. Let us know if you'd like to rebook."
