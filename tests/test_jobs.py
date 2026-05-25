from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.models import TimeSlot, Job, JobStatus, Technician, Customer


async def _make_job(db, business, status=JobStatus.confirmed, source="ai", estimate=200):
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()
    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id).limit(1)
    )).scalar_one()

    now = datetime.now(timezone.utc)
    slot = TimeSlot(
        technician_id=tech.id,
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=3),
        is_available=False,
    )
    db.add(slot)
    await db.flush()

    job = Job(
        business_id=business.id,
        customer_id=cust.id,
        technician_id=tech.id,
        time_slot_id=slot.id,
        job_type="Drain cleaning",
        status=status,
        source=source,
        estimate=estimate,
    )
    db.add(job)
    await db.commit()
    return job


async def test_list_jobs_empty(client, business):
    r = await client.get("/jobs")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_jobs(client, business, db):
    await _make_job(db, business)
    r = await client.get("/jobs")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) == 1
    assert jobs[0]["job_type"] == "Drain cleaning"
    assert jobs[0]["estimate"] == 200
    assert jobs[0]["start_time"] is not None
    assert jobs[0]["end_time"] is not None


async def test_get_job(client, business, db):
    job = await _make_job(db, business)
    r = await client.get(f"/jobs/{job.id}")
    assert r.status_code == 200
    assert r.json()["id"] == job.id


async def test_get_job_404(client, business):
    r = await client.get("/jobs/9999")
    assert r.status_code == 404


async def test_update_job_status(client, business, db):
    job = await _make_job(db, business)
    r = await client.patch(f"/jobs/{job.id}/status?status=completed")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


async def test_cancelling_job_frees_the_slot(client, business, db):
    job = await _make_job(db, business)
    slot_id = job.time_slot_id

    # Cancel via the API
    r = await client.patch(f"/jobs/{job.id}/status?status=cancelled")
    assert r.status_code == 200

    # Slot should be available again
    from sqlalchemy import select
    slot = (await db.execute(select(TimeSlot).where(TimeSlot.id == slot_id))).scalar_one()
    await db.refresh(slot)
    assert slot.is_available is True


async def test_create_job_manual(client, business, db):
    # Create a free slot first
    tech = (await db.execute(select(Technician).where(Technician.business_id == business.id).limit(1))).scalar_one()
    cust = (await db.execute(select(Customer).where(Customer.business_id == business.id).limit(1))).scalar_one()
    now = datetime.now(timezone.utc)
    slot = TimeSlot(technician_id=tech.id, start_time=now + timedelta(days=1), end_time=now + timedelta(days=1, hours=1), is_available=True)
    db.add(slot)
    await db.commit()

    r = await client.post("/jobs", json={
        "customer_id": cust.id,
        "time_slot_id": slot.id,
        "job_type": "Leak repair",
        "estimate": 250,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["job_type"] == "Leak repair"
    assert body["source"] == "human"
    assert body["estimate"] == 250

    # Slot should now be unavailable
    await db.refresh(slot)
    assert slot.is_available is False


async def test_create_job_rejects_unavailable_slot(client, business, db):
    job = await _make_job(db, business)  # this slot is already claimed
    cust = (await db.execute(select(Customer).where(Customer.business_id == business.id).limit(1))).scalar_one()

    r = await client.post("/jobs", json={
        "customer_id": cust.id,
        "time_slot_id": job.time_slot_id,
        "job_type": "Drain cleaning",
    })
    assert r.status_code == 400


async def test_reschedule_job(client, business, db):
    job = await _make_job(db, business)
    old_slot_id = job.time_slot_id

    tech = (await db.execute(select(Technician).where(Technician.business_id == business.id).limit(1))).scalar_one()
    now = datetime.now(timezone.utc)
    new_slot = TimeSlot(technician_id=tech.id, start_time=now + timedelta(days=3), end_time=now + timedelta(days=3, hours=1), is_available=True)
    db.add(new_slot)
    await db.commit()

    r = await client.patch(f"/jobs/{job.id}/reschedule", json={"new_slot_id": new_slot.id})
    assert r.status_code == 200
    body = r.json()
    assert body["start_time"] is not None

    # Old slot freed, new slot claimed
    old_slot = (await db.execute(select(TimeSlot).where(TimeSlot.id == old_slot_id))).scalar_one()
    await db.refresh(old_slot)
    await db.refresh(new_slot)
    assert old_slot.is_available is True
    assert new_slot.is_available is False


async def test_reschedule_404(client, business):
    r = await client.patch("/jobs/9999/reschedule", json={"new_slot_id": 1})
    assert r.status_code == 404


async def test_reschedule_reactivates_cancelled_job(client, business, db):
    """When picking a new slot for a cancelled job, the job should re-confirm."""
    job = await _make_job(db, business, status=JobStatus.cancelled)

    tech = (await db.execute(select(Technician).where(Technician.business_id == business.id).limit(1))).scalar_one()
    now = datetime.now(timezone.utc)
    new_slot = TimeSlot(
        technician_id=tech.id,
        start_time=now + timedelta(days=4),
        end_time=now + timedelta(days=4, hours=1),
        is_available=True,
    )
    db.add(new_slot)
    await db.commit()

    r = await client.patch(f"/jobs/{job.id}/reschedule", json={"new_slot_id": new_slot.id})
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"


async def test_create_job_rejects_customer_from_other_business(client, business, db):
    """Multi-tenancy guard: client (business_id=1) can't book a customer from another business."""
    from app.models import Business as BusinessModel, Customer as CustomerModel

    other = BusinessModel(name="Other Co", twilio_number="+15550009999")
    db.add(other)
    await db.flush()
    other_cust = CustomerModel(business_id=other.id, name="Outsider", phone="+15550001234")
    db.add(other_cust)

    # A valid slot in OUR business
    tech = (await db.execute(select(Technician).where(Technician.business_id == business.id).limit(1))).scalar_one()
    now = datetime.now(timezone.utc)
    slot = TimeSlot(technician_id=tech.id, start_time=now + timedelta(days=1), end_time=now + timedelta(days=1, hours=1), is_available=True)
    db.add(slot)
    await db.commit()

    r = await client.post("/jobs", json={
        "customer_id": other_cust.id,
        "time_slot_id": slot.id,
        "job_type": "Drain cleaning",
    })
    assert r.status_code == 404  # Customer not found (in our business)


async def test_reschedule_rejects_slot_from_other_business(client, business, db):
    """Multi-tenancy: can't reschedule to a slot belonging to another business's tech."""
    from app.models import Business as BusinessModel

    job = await _make_job(db, business)

    other = BusinessModel(name="Other Co", twilio_number="+15550008888")
    db.add(other)
    await db.flush()
    other_tech = Technician(business_id=other.id, name="Stranger", phone="+15550005678")
    db.add(other_tech)
    await db.flush()

    now = datetime.now(timezone.utc)
    bad_slot = TimeSlot(
        technician_id=other_tech.id,
        start_time=now + timedelta(days=2),
        end_time=now + timedelta(days=2, hours=1),
        is_available=True,
    )
    db.add(bad_slot)
    await db.commit()

    r = await client.patch(f"/jobs/{job.id}/reschedule", json={"new_slot_id": bad_slot.id})
    assert r.status_code == 400


async def test_create_job_missing_required_field(client, business, db):
    cust = (await db.execute(select(Customer).where(Customer.business_id == business.id).limit(1))).scalar_one()
    # Missing time_slot_id
    r = await client.post("/jobs", json={"customer_id": cust.id, "job_type": "Drain cleaning"})
    assert r.status_code == 422
