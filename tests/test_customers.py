async def test_list_customers(client, business):
    r = await client.get("/customers")
    assert r.status_code == 200
    customers = r.json()
    assert len(customers) == 1
    assert customers[0]["name"] == "Casey Customer"
    assert customers[0]["job_count"] == 0


async def test_search_customers(client, business):
    # Match by name
    r = await client.get("/customers?q=casey")
    assert len(r.json()) == 1
    # No match
    r = await client.get("/customers?q=nobody")
    assert r.json() == []


async def test_pagination(client, business):
    r = await client.get("/customers?limit=5&offset=0")
    assert r.status_code == 200
    r = await client.get("/customers?limit=0")
    assert r.status_code == 422  # ge=1 constraint


async def test_customer_job_count_reflects_real_jobs(client, business, db):
    """job_count on /customers should match the number of jobs that customer has —
    the frontend uses this to display per-customer job counts."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from app.models import Customer, Technician, TimeSlot, Job, JobStatus

    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id).limit(1)
    )).scalar_one()
    tech = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalar_one()

    now = datetime.now(timezone.utc)
    for i in range(3):
        slot = TimeSlot(
            technician_id=tech.id,
            start_time=now + timedelta(days=i + 1),
            end_time=now + timedelta(days=i + 1, hours=1),
            is_available=False,
        )
        db.add(slot)
        await db.flush()
        db.add(Job(
            business_id=business.id, customer_id=cust.id, technician_id=tech.id,
            time_slot_id=slot.id, job_type="Test",
            status=JobStatus.completed if i == 0 else JobStatus.confirmed,
            source="ai", estimate=100,
        ))
    await db.commit()

    r = await client.get("/customers")
    body = r.json()
    target = next(c for c in body if c["id"] == cust.id)
    assert target["job_count"] == 3
