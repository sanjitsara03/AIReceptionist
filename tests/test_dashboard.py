from datetime import datetime, timezone, timedelta
from sqlalchemy import select

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

    # Schedule the slot 30 minutes after "today midnight UTC" so it's always today,
    # regardless of when the test runs. (Old logic flaked between 23:00–00:00 UTC.)
    now = datetime.now(timezone.utc)
    later_today = now.replace(hour=0, minute=30, second=0, microsecond=0)
    if later_today < now - timedelta(minutes=5):
        # Already past 00:30 today UTC — just pick a safe slot a few minutes from now.
        later_today = now + timedelta(minutes=5)

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
