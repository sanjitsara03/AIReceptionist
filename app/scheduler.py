import asyncio
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from twilio.rest import Client

from app.database import AsyncSessionLocal
from app.models import Job, JobStatus, Business, TimeSlot
from app.config import settings

scheduler = AsyncIOScheduler()
twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)


async def send_reminders():
    """Send a 24-hour SMS reminder for confirmed jobs starting within the next 24h."""
    now = datetime.now(timezone.utc)
    window = now + timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job)
            .join(TimeSlot, Job.time_slot_id == TimeSlot.id)
            .where(
                Job.status == JobStatus.confirmed,
                Job.reminder_sent == False,
                TimeSlot.start_time >= now,
                TimeSlot.start_time <= window,
            )
            .options(
                selectinload(Job.customer),
                selectinload(Job.time_slot),
            )
        )
        jobs = result.scalars().all()

        sent = 0
        for job in jobs:
            business_result = await db.execute(
                select(Business).where(Business.id == job.business_id)
            )
            business = business_result.scalar_one_or_none()

            if not job.customer or not business or not job.time_slot:
                continue

            message = (
                f"Reminder: Your {job.job_type} appointment with {business.name} is tomorrow at "
                f"{job.time_slot.start_time.strftime('%I:%M %p')}. Reply STOP to opt out."
            )

            # Twilio's SDK is sync — run it in a thread so the event loop
            # stays responsive to incoming webhooks while we wait on Twilio.
            await asyncio.to_thread(
                twilio_client.messages.create,
                body=message,
                from_=business.twilio_number,
                to=job.customer.phone,
            )

            job.reminder_sent = True
            sent += 1

        await db.commit()
        print(f"[Reminders] Sent {sent} reminders.")


async def detect_no_shows():
    """Mark confirmed jobs that ended >2h ago as no_show.

    The 2-hour buffer prevents flipping jobs that the tech actually
    completed but hasn't been marked complete yet.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job)
            .join(TimeSlot, Job.time_slot_id == TimeSlot.id)
            .where(
                Job.status == JobStatus.confirmed,
                TimeSlot.end_time < cutoff,
            )
        )
        jobs = result.scalars().all()

        for job in jobs:
            job.status = JobStatus.no_show

        await db.commit()
        print(f"[No-shows] Marked {len(jobs)} jobs as no-show.")


async def send_daily_digest():
    """Send each business owner a morning summary of today's jobs."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        businesses_result = await db.execute(select(Business))
        businesses = businesses_result.scalars().all()

        for business in businesses:
            result = await db.execute(
                select(Job)
                .join(TimeSlot, Job.time_slot_id == TimeSlot.id)
                .where(
                    Job.business_id == business.id,
                    TimeSlot.start_time >= today_start,
                    TimeSlot.start_time < today_end,
                )
            )
            jobs = result.scalars().all()

            if not jobs:
                continue

            confirmed = sum(1 for j in jobs if j.status == JobStatus.confirmed)
            completed = sum(1 for j in jobs if j.status == JobStatus.completed)
            no_show = sum(1 for j in jobs if j.status == JobStatus.no_show)
            cancelled = sum(1 for j in jobs if j.status == JobStatus.cancelled)

            # Digest delivery is intentionally a no-op until an owner_phone
            # field is added to Business. The previous behavior texted "the
            # first technician" which surprised techs and leaked metrics to
            # the wrong person. Logging the digest so it still shows up in
            # Railway logs / Sentry breadcrumbs for the owner to see.
            print(
                f"[Digest] {business.name}: confirmed={confirmed} "
                f"completed={completed} no_shows={no_show} cancelled={cancelled}"
            )

        print("[Digest] Daily digest run complete.")


def start_scheduler():
    scheduler.add_job(send_reminders, "interval", hours=1, id="send_reminders")
    scheduler.add_job(detect_no_shows, "interval", hours=1, id="detect_no_shows")
    scheduler.add_job(send_daily_digest, "cron", hour=8, minute=0, id="daily_digest")
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown()
