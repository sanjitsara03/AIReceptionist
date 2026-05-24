from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, func
from twilio.rest import Client

from app.database import AsyncSessionLocal
from app.models import Job, JobStatus, Customer, Business, Technician
from app.config import settings

scheduler = AsyncIOScheduler()
twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)


async def send_reminders():
    now = datetime.now(timezone.utc)
    window = now + timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job)
            .where(
                Job.status == JobStatus.confirmed,
                Job.reminder_sent == False,
                Job.start_time >= now,
                Job.start_time <= window,
            )
        )
        jobs = result.scalars().all()

        for job in jobs:
            customer_result = await db.execute(select(Customer).where(Customer.id == job.customer_id))
            customer = customer_result.scalar_one_or_none()

            business_result = await db.execute(select(Business).where(Business.id == job.business_id))
            business = business_result.scalar_one_or_none()

            if not customer or not business:
                continue

            message = (
                f"Reminder: Your {job.job_type} appointment with {business.name} is tomorrow at "
                f"{job.start_time.strftime('%I:%M %p')}. Reply STOP to opt out."
            )

            twilio_client.messages.create(
                body=message,
                from_=business.twilio_number,
                to=customer.phone,
            )

            job.reminder_sent = True

        await db.commit()
        print(f"[Reminders] Sent {len(jobs)} reminders.")


async def detect_no_shows():
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job).where(
                Job.status == JobStatus.confirmed,
                Job.start_time < now,
            )
        )
        jobs = result.scalars().all()

        for job in jobs:
            job.status = JobStatus.no_show

        await db.commit()
        print(f"[No-shows] Marked {len(jobs)} jobs as no-show.")


async def send_daily_digest():
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        businesses_result = await db.execute(select(Business))
        businesses = businesses_result.scalars().all()

        for business in businesses:
            result = await db.execute(
                select(Job).where(
                    Job.business_id == business.id,
                    Job.start_time >= today_start,
                    Job.start_time < today_end,
                )
            )
            jobs = result.scalars().all()

            if not jobs:
                continue

            confirmed = sum(1 for j in jobs if j.status == JobStatus.confirmed)
            completed = sum(1 for j in jobs if j.status == JobStatus.completed)
            no_show = sum(1 for j in jobs if j.status == JobStatus.no_show)
            cancelled = sum(1 for j in jobs if j.status == JobStatus.cancelled)

            # Get business owner — first technician for now
            tech_result = await db.execute(
                select(Technician).where(Technician.business_id == business.id).limit(1)
            )
            owner = tech_result.scalar_one_or_none()

            if not owner:
                continue

            message = (
                f"Good morning! Today's summary for {business.name}:\n"
                f"Confirmed: {confirmed}\n"
                f"Completed: {completed}\n"
                f"No-shows: {no_show}\n"
                f"Cancelled: {cancelled}"
            )

            twilio_client.messages.create(
                body=message,
                from_=business.twilio_number,
                to=owner.phone,
            )

        print("[Digest] Daily digest sent.")


def start_scheduler():
    scheduler.add_job(send_reminders, "interval", hours=1, id="send_reminders")
    scheduler.add_job(detect_no_shows, "interval", hours=1, id="detect_no_shows")
    scheduler.add_job(send_daily_digest, "cron", hour=8, minute=0, id="daily_digest")
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown()
