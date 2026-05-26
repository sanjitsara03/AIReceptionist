from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.config import BUSINESS_TZ
from app.models import TimeSlot, Job, JobStatus, Technician, Customer, Conversation, MessageDirection


async def test_summary_empty(client, business):
    r = await client.get("/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total_jobs_today"] == 0
    assert body["ai_booked_today"] == 0
    assert body["ai_booked_revenue"] == 0
    assert body["total_customers"] == 1


async def test_summary_counts_today(client, business, db):
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()
    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id).limit(1)
    )).scalar_one()

    # Dashboard "today" is in PT (America/Los_Angeles), so anchor the slot
    # to PT-midnight + 30 minutes and convert to UTC for storage.
    now_pt = datetime.now(BUSINESS_TZ)
    later_pt = now_pt.replace(hour=0, minute=30, second=0, microsecond=0)
    if later_pt.astimezone(timezone.utc) < datetime.now(timezone.utc) - timedelta(minutes=5):
        # 00:30 PT today is already past — pick a safe slot a few minutes from now.
        later_pt = now_pt + timedelta(minutes=5)
    later_today = later_pt.astimezone(timezone.utc)

    slot = TimeSlot(technician_id=tech.id, start_time=later_today, end_time=later_today + timedelta(hours=1), is_available=False)
    db.add(slot)
    await db.flush()
    db.add(Job(
        business_id=business.id, customer_id=cust.id, technician_id=tech.id,
        time_slot_id=slot.id, job_type="Drain cleaning",
        status=JobStatus.confirmed, source="ai", estimate=180,
    ))
    await db.commit()

    r = await client.get("/dashboard/summary")
    body = r.json()
    assert body["total_jobs_today"] == 1
    assert body["confirmed"] == 1
    assert body["ai_booked_today"] == 1
    assert body["ai_booked_revenue"] == 180


async def test_feed_empty(client, business):
    r = await client.get("/dashboard/feed")
    assert r.status_code == 200
    assert r.json() == []
