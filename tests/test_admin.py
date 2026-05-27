"""Tests for the platform admin endpoints under /admin/."""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.config import settings
from app.models import Business, Customer, Job, JobStatus, TimeSlot, Technician, Conversation, Message, MessageDirection, Invite


# auth

async def test_admin_requires_secret_header(client, business):
    """Without the X-Admin-Secret header, every admin endpoint should 422."""
    for path in ("/admin/businesses", "/admin/invites?business_id=1"):
        r = await client.get(path)
        assert r.status_code == 422, f"GET {path}: expected 422, got {r.status_code}"

    r = await client.post("/admin/businesses", json={"name": "x", "twilio_number": "+15550000"})
    assert r.status_code == 422

    r = await client.delete("/admin/businesses/1")
    assert r.status_code == 422


async def test_admin_rejects_wrong_secret(client, business):
    r = await client.get("/admin/businesses", headers={"X-Admin-Secret": "nope"})
    assert r.status_code == 403


# list

async def test_list_businesses_includes_counts(client, business, db):
    """The list endpoint reports per-business customer/job/conversation counts."""
    tech = (await db.execute(select(Technician).where(Technician.business_id == business.id).limit(1))).scalar_one()
    cust = (await db.execute(select(Customer).where(Customer.business_id == business.id).limit(1))).scalar_one()

    # Add a job, conversation, and message under business 1
    now = datetime.now(timezone.utc)
    slot = TimeSlot(technician_id=tech.id, start_time=now + timedelta(hours=1),
                    end_time=now + timedelta(hours=2), is_available=False)
    db.add(slot)
    await db.flush()
    db.add(Job(business_id=business.id, customer_id=cust.id, technician_id=tech.id,
               time_slot_id=slot.id, job_type="Test", status=JobStatus.confirmed,
               source="ai", estimate=100))
    conv = Conversation(customer_id=cust.id, channel="sms")
    db.add(conv)
    await db.flush()
    db.add(Message(conversation_id=conv.id, direction=MessageDirection.inbound, body="hi"))
    await db.commit()

    r = await client.get("/admin/businesses", headers={"X-Admin-Secret": settings.admin_secret})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    b = body[0]
    assert b["customer_count"] == 1
    assert b["job_count"] == 1
    assert b["conversation_count"] == 1
    # Sensitive owner_auth0_id IS exposed to admin
    assert b["owner_auth0_id"] == "test|user-1"


# create

async def test_create_business(client, business):
    """Happy path: create returns the new business with zero counts."""
    payload = {
        "name": "Mike's HVAC",
        "twilio_number": "+15550009999",
        "address": "1 Cool St",
        "system_prompt": "You are Mike's AI receptionist.",
    }
    r = await client.post("/admin/businesses", json=payload,
                          headers={"X-Admin-Secret": settings.admin_secret})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Mike's HVAC"
    assert body["twilio_number"] == "+15550009999"
    assert body["customer_count"] == 0
    assert body["owner_auth0_id"] is None


async def test_create_business_duplicate_twilio_number(client, business):
    """Duplicate twilio_number should return 409, not 500."""
    r = await client.post(
        "/admin/businesses",
        json={"name": "Conflict Co", "twilio_number": business.twilio_number},
        headers={"X-Admin-Secret": settings.admin_secret},
    )
    assert r.status_code == 409


# delete

async def test_delete_business_cascades(client, business, db):
    """Deleting a business removes all dependent rows (no orphans left)."""
    # Add some children
    tech = (await db.execute(select(Technician).where(Technician.business_id == business.id).limit(1))).scalar_one()
    cust = (await db.execute(select(Customer).where(Customer.business_id == business.id).limit(1))).scalar_one()
    now = datetime.now(timezone.utc)
    slot = TimeSlot(technician_id=tech.id, start_time=now + timedelta(hours=1),
                    end_time=now + timedelta(hours=2), is_available=False)
    db.add(slot)
    await db.flush()
    db.add(Job(business_id=business.id, customer_id=cust.id, technician_id=tech.id,
               time_slot_id=slot.id, job_type="Test", status=JobStatus.confirmed,
               source="ai", estimate=100))
    conv = Conversation(customer_id=cust.id, channel="sms")
    db.add(conv)
    await db.flush()
    db.add(Message(conversation_id=conv.id, direction=MessageDirection.inbound, body="hi"))
    db.add(Invite(token="tok-abc", business_id=business.id,
                  expires_at=now + timedelta(days=7)))
    await db.commit()

    r = await client.delete(f"/admin/businesses/{business.id}",
                            headers={"X-Admin-Secret": settings.admin_secret})
    assert r.status_code == 204

    # Verify cascade ; every related row is gone
    for model in (Business, Customer, Technician, TimeSlot, Job, Conversation, Message, Invite):
        count = (await db.execute(select(model))).scalars().all()
        assert len(count) == 0, f"orphan rows in {model.__tablename__}: {len(count)}"


async def test_delete_nonexistent_business(client, business):
    r = await client.delete("/admin/businesses/9999",
                            headers={"X-Admin-Secret": settings.admin_secret})
    assert r.status_code == 404


# invites listing

async def test_admin_invites_list_filters_by_business(client, business, db):
    """Invites for one business shouldn't leak into another's list."""
    # business A (existing test fixture, id=1)
    db.add_all([
        Invite(token="a-1", business_id=business.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7)),
        Invite(token="a-2", business_id=business.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7),
               claimed_at=datetime.now(timezone.utc)),
    ])
    # business B (new)
    other = Business(name="Other Co", twilio_number="+15550008888")
    db.add(other)
    await db.flush()
    db.add(Invite(token="b-1", business_id=other.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
    await db.commit()

    r = await client.get(f"/admin/invites?business_id={business.id}",
                         headers={"X-Admin-Secret": settings.admin_secret})
    assert r.status_code == 200
    tokens = {i["token"] for i in r.json()}
    assert tokens == {"a-1", "a-2"}

    r = await client.get(f"/admin/invites?business_id={other.id}",
                         headers={"X-Admin-Secret": settings.admin_secret})
    assert {i["token"] for i in r.json()} == {"b-1"}


async def test_admin_invites_404_for_unknown_business(client, business):
    r = await client.get("/admin/invites?business_id=9999",
                         headers={"X-Admin-Secret": settings.admin_secret})
    assert r.status_code == 404
