from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.models import TimeSlot, Technician, Job, JobStatus, Customer


async def test_available_slots_empty(client, business):
    r = await client.get("/timeslots/available")
    assert r.status_code == 200
    assert r.json() == []


async def test_available_slots_returns_future_open_slots_only(client, business, db):
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()

    now = datetime.now(timezone.utc)
    db.add_all([
        # Future, open ; should appear
        TimeSlot(technician_id=tech.id, start_time=now + timedelta(days=1),
                 end_time=now + timedelta(days=1, hours=1), is_available=True),
        # Future, taken ; should NOT appear
        TimeSlot(technician_id=tech.id, start_time=now + timedelta(days=2),
                 end_time=now + timedelta(days=2, hours=1), is_available=False),
        # Past, open ; should NOT appear
        TimeSlot(technician_id=tech.id, start_time=now - timedelta(days=1),
                 end_time=now - timedelta(days=1) + timedelta(hours=1), is_available=True),
    ])
    await db.commit()

    r = await client.get("/timeslots/available")
    body = r.json()
    assert len(body) == 1
    assert body[0]["technician_name"] == tech.name
    assert body[0]["technician_id"] == tech.id


async def test_available_slots_respects_days_window(client, business, db):
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()
    now = datetime.now(timezone.utc)
    db.add(TimeSlot(
        technician_id=tech.id,
        start_time=now + timedelta(days=10),
        end_time=now + timedelta(days=10, hours=1),
        is_available=True,
    ))
    await db.commit()

    r = await client.get("/timeslots/available?days=5")
    assert r.json() == []

    r = await client.get("/timeslots/available?days=30")
    assert len(r.json()) == 1


# list all slots (booked + free)

async def test_list_all_slots_includes_booked(client, business, db):
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()
    now = datetime.now(timezone.utc)
    db.add_all([
        TimeSlot(technician_id=tech.id, start_time=now + timedelta(days=1),
                 end_time=now + timedelta(days=1, hours=1), is_available=True),
        TimeSlot(technician_id=tech.id, start_time=now + timedelta(days=2),
                 end_time=now + timedelta(days=2, hours=1), is_available=False),
    ])
    await db.commit()

    r = await client.get("/timeslots")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert {s["is_available"] for s in body} == {True, False}


# create single slot

async def test_create_slot(client, business, db):
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()
    now = datetime.now(timezone.utc)
    r = await client.post("/timeslots", json={
        "technician_id": tech.id,
        "start_time": (now + timedelta(days=1)).isoformat(),
        "end_time": (now + timedelta(days=1, hours=2)).isoformat(),
    })
    assert r.status_code == 201
    body = r.json()
    assert body["is_available"] is True
    assert body["technician_name"] == tech.name


async def test_create_slot_invalid_time_range(client, business, db):
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()
    now = datetime.now(timezone.utc)
    r = await client.post("/timeslots", json={
        "technician_id": tech.id,
        "start_time": (now + timedelta(days=1, hours=2)).isoformat(),
        "end_time": (now + timedelta(days=1)).isoformat(),
    })
    assert r.status_code == 400


async def test_create_slot_rejects_other_business_tech(client, business, db):
    from app.models import Business as B
    other = B(name="Other Co", twilio_number="+15550007777")
    db.add(other)
    await db.flush()
    other_tech = Technician(business_id=other.id, name="Outsider", phone="+15550001234")
    db.add(other_tech)
    await db.commit()

    now = datetime.now(timezone.utc)
    r = await client.post("/timeslots", json={
        "technician_id": other_tech.id,
        "start_time": (now + timedelta(days=1)).isoformat(),
        "end_time": (now + timedelta(days=1, hours=1)).isoformat(),
    })
    assert r.status_code == 404


# bulk create

async def test_bulk_create_weekdays(client, business, db):
    """5 weekdays × (17-9 = 8 hours)/2hr slot = 5 × 4 = 20 slots."""
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # Make a Monday → next Monday window (covers exactly Mon Sun)
    days_until_monday = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=days_until_monday)
    end = start + timedelta(days=7)

    r = await client.post("/timeslots/bulk", json={
        "technician_id": tech.id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "weekdays": [0, 1, 2, 3, 4],  # Mon-Fri
        "day_start_hour": 9,
        "day_end_hour": 17,
        "slot_minutes": 120,
    })
    assert r.status_code == 201
    body = r.json()
    assert len(body) == 5 * 4  # 5 weekdays, 4 slots each


async def test_bulk_create_rejects_huge_range(client, business, db):
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()
    now = datetime.now(timezone.utc)
    r = await client.post("/timeslots/bulk", json={
        "technician_id": tech.id,
        "start_date": now.isoformat(),
        "end_date": (now + timedelta(days=200)).isoformat(),
        "weekdays": [0, 1, 2, 3, 4],
        "day_start_hour": 9,
        "day_end_hour": 17,
        "slot_minutes": 60,
    })
    assert r.status_code == 400  # capped at 90 days


# delete slot

async def test_delete_available_slot(client, business, db):
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()
    now = datetime.now(timezone.utc)
    slot = TimeSlot(
        technician_id=tech.id,
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=1),
        is_available=True,
    )
    db.add(slot)
    await db.commit()

    r = await client.delete(f"/timeslots/{slot.id}")
    assert r.status_code == 204

    gone = (await db.execute(
        select(TimeSlot).where(TimeSlot.id == slot.id)
    )).scalar_one_or_none()
    assert gone is None


async def test_delete_booked_slot_rejected(client, business, db):
    """Cannot delete a slot that has a job attached — must cancel the job first."""
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()
    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id).limit(1)
    )).scalar_one()
    now = datetime.now(timezone.utc)
    slot = TimeSlot(
        technician_id=tech.id,
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=1),
        is_available=False,
    )
    db.add(slot)
    await db.flush()
    db.add(Job(
        business_id=business.id, customer_id=cust.id, technician_id=tech.id,
        time_slot_id=slot.id, job_type="Drain cleaning",
        status=JobStatus.confirmed, source="ai", estimate=180,
    ))
    await db.commit()

    r = await client.delete(f"/timeslots/{slot.id}")
    assert r.status_code == 409


async def test_delete_slot_from_other_business_returns_404(client, business, db):
    from app.models import Business as B
    other = B(name="Other Co", twilio_number="+15550006666")
    db.add(other)
    await db.flush()
    other_tech = Technician(business_id=other.id, name="Outsider", phone="+15550001234")
    db.add(other_tech)
    await db.flush()
    now = datetime.now(timezone.utc)
    foreign_slot = TimeSlot(
        technician_id=other_tech.id,
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=1),
        is_available=True,
    )
    db.add(foreign_slot)
    await db.commit()

    r = await client.delete(f"/timeslots/{foreign_slot.id}")
    assert r.status_code == 404
