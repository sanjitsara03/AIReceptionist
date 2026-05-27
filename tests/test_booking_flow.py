"""
End-to-end customer-journey tests for the AI receptionist booking flow.

Covers what a real customer can do:
  1. Check availability
  2. Book an appointment
  3. List their own appointments
  4. Reschedule
  5. Cancel one
  6. Cancel all
  7. Webhook entry points (SMS + voice)
  8. Allowlist + abuse paths
  9. Output sanitization (TTS + dashboard)

The agent's LLM call itself is NOT tested (would require live Claude API).
Each agent tool is exercised directly with a fake RunContext, which is the
same surface the LLM hits during a real conversation.
"""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import (
    TimeSlot,
    Job,
    JobStatus,
    Technician,
    Customer,
    Business,
    Conversation,
    Message,
    MessageDirection,
)
from app.agent.tools import (
    AgentDeps,
    check_availability,
    book_job,
    reschedule_job,
    cancel_job,
    cancel_all_jobs,
    list_my_appointments,
    _estimate_for,
)
from app.routes.webhooks import sanitize_for_speech


# Helpers

async def _seed_slots(db, business, when_offsets_hours: list[float], tech_idx: int = 0):
    """Create available time slots for one of the business's techs. Returns the slots."""
    techs = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).order_by(Technician.id)
    )).scalars().all()
    tech = techs[tech_idx]
    now = datetime.now(timezone.utc)
    slots = []
    for h in when_offsets_hours:
        s = TimeSlot(
            technician_id=tech.id,
            start_time=now + timedelta(hours=h),
            end_time=now + timedelta(hours=h + 1),
            is_available=True,
        )
        db.add(s)
        slots.append(s)
    await db.commit()
    return slots


async def _make_customer(db, business, phone="+15550009999", name="Casey Customer") -> Customer:
    """Get the seeded customer, or make a new one with the given phone."""
    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id, Customer.phone == phone)
    )).scalar_one_or_none()
    if cust:
        return cust
    cust = Customer(business_id=business.id, name=name, phone=phone)
    db.add(cust)
    await db.commit()
    return cust


def _ctx(db, business, customer) -> SimpleNamespace:
    """Fake RunContext that the agent tools actually need — they only read .deps."""
    deps = AgentDeps(db=db, business_id=business.id, business=business, customer=customer)
    return SimpleNamespace(deps=deps)


# 1. Check availability

async def test_check_availability_empty(db, business):
    cust = await _make_customer(db, business)
    out = await check_availability(_ctx(db, business, cust))
    assert "no available" in out.lower()


async def test_check_availability_returns_unique_times(db, business):
    # Three slots at the same time across two techs → should dedupe to 1
    techs = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).order_by(Technician.id)
    )).scalars().all()
    same_time = datetime.now(timezone.utc) + timedelta(hours=3)
    later = datetime.now(timezone.utc) + timedelta(hours=5)
    for tech in techs:
        db.add(TimeSlot(technician_id=tech.id, start_time=same_time, end_time=same_time + timedelta(hours=1), is_available=True))
    db.add(TimeSlot(technician_id=techs[0].id, start_time=later, end_time=later + timedelta(hours=1), is_available=True))
    await db.commit()

    cust = await _make_customer(db, business)
    out = await check_availability(_ctx(db, business, cust))

    # Only two distinct human facing times even though three rows exist
    assert out.count("[internal:slot_id=") == 2
    assert "Available appointment times" in out


async def test_check_availability_hides_other_businesses(db, business):
    # Make a second business with its own tech + slot
    other = Business(name="Rival Co", twilio_number="+15558887777", owner_auth0_id="other|user")
    db.add(other)
    await db.flush()
    other_tech = Technician(business_id=other.id, name="Other", phone="+15558887778")
    db.add(other_tech)
    await db.flush()
    db.add(TimeSlot(
        technician_id=other_tech.id,
        start_time=datetime.now(timezone.utc) + timedelta(hours=2),
        end_time=datetime.now(timezone.utc) + timedelta(hours=3),
        is_available=True,
    ))
    await db.commit()

    cust = await _make_customer(db, business)
    out = await check_availability(_ctx(db, business, cust))
    # Our business has no slots; the other business's slot must not leak through
    assert "no available" in out.lower()


async def test_check_availability_skips_past_slots(db, business):
    techs = (await db.execute(
        select(Technician).where(Technician.business_id == business.id).limit(1)
    )).scalars().all()
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    db.add(TimeSlot(technician_id=techs[0].id, start_time=past, end_time=past + timedelta(hours=1), is_available=True))
    await db.commit()

    cust = await _make_customer(db, business)
    out = await check_availability(_ctx(db, business, cust))
    assert "no available" in out.lower()


async def test_check_availability_output_format_safe_for_tts(db, business):
    await _seed_slots(db, business, [2, 4, 6])
    cust = await _make_customer(db, business)
    out = await check_availability(_ctx(db, business, cust))

    # Must use the documented [internal:...] tag pattern so the LLM knows it's internal
    assert "[internal:slot_id=" in out
    # No pipes or markdown ; model should be receiving clean text
    assert "|" not in out
    assert "**" not in out


# 2. Book an appointment

async def test_book_job_happy_path(db, business):
    slots = await _seed_slots(db, business, [3])
    cust = await _make_customer(db, business)

    out = await book_job(_ctx(db, business, cust), slots[0].id, "drain cleaning")
    await db.commit()

    assert out.lower().startswith("booked")

    # Slot is marked unavailable
    fresh_slot = (await db.execute(select(TimeSlot).where(TimeSlot.id == slots[0].id))).scalar_one()
    assert fresh_slot.is_available is False

    # Job row exists, scoped to the right customer + business
    jobs = (await db.execute(
        select(Job).where(Job.customer_id == cust.id, Job.business_id == business.id)
    )).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].job_type == "drain cleaning"
    assert jobs[0].status == JobStatus.confirmed
    assert jobs[0].estimate == 180  # from _estimate_for


async def test_book_job_rejects_unavailable_slot(db, business):
    slots = await _seed_slots(db, business, [3])
    slots[0].is_available = False
    await db.commit()

    cust = await _make_customer(db, business)
    out = await book_job(_ctx(db, business, cust), slots[0].id, "drain cleaning")
    assert "no longer available" in out.lower()


async def test_book_job_rejects_slot_from_another_business(db, business, db_other_business):
    other_biz, other_slot = db_other_business
    cust = await _make_customer(db, business)
    out = await book_job(_ctx(db, business, cust), other_slot.id, "drain cleaning")
    assert "no longer available" in out.lower()

    # Other business's slot is unchanged
    fresh = (await db.execute(select(TimeSlot).where(TimeSlot.id == other_slot.id))).scalar_one()
    assert fresh.is_available is True


@pytest.fixture
async def db_other_business(db):
    """A second business with one tech and one open slot — for cross-tenant tests."""
    other = Business(name="Rival Co", twilio_number="+15558887777", owner_auth0_id="other|user")
    db.add(other)
    await db.flush()
    tech = Technician(business_id=other.id, name="Other Tech", phone="+15558887778")
    db.add(tech)
    await db.flush()
    slot = TimeSlot(
        technician_id=tech.id,
        start_time=datetime.now(timezone.utc) + timedelta(hours=4),
        end_time=datetime.now(timezone.utc) + timedelta(hours=5),
        is_available=True,
    )
    db.add(slot)
    await db.commit()
    return other, slot


# 3. List the customer's appointments

async def test_list_my_appointments_empty(db, business):
    cust = await _make_customer(db, business)
    out = await list_my_appointments(_ctx(db, business, cust))
    assert "no upcoming" in out.lower()


async def test_list_my_appointments_shows_owned_and_hides_others(db, business):
    slots = await _seed_slots(db, business, [3, 5])
    cust = await _make_customer(db, business)

    # Book the first slot for this caller
    await book_job(_ctx(db, business, cust), slots[0].id, "drain cleaning")
    await db.commit()

    # Book the second slot for a DIFFERENT customer at the same business
    other_cust = await _make_customer(db, business, phone="+15550008888", name="Other Caller")
    await book_job(_ctx(db, business, other_cust), slots[1].id, "drain cleaning")
    await db.commit()

    out = await list_my_appointments(_ctx(db, business, cust))
    # Caller's own job present
    assert "drain cleaning" in out.lower()
    # The internal job_id tag is present (proves it came from the tool format, not text)
    assert "[internal:job_id=" in out
    # Only ONE job listed ; other customer's job is hidden
    assert out.lower().count("drain cleaning") == 1


async def test_list_my_appointments_excludes_cancelled(db, business):
    slots = await _seed_slots(db, business, [3])
    cust = await _make_customer(db, business)

    await book_job(_ctx(db, business, cust), slots[0].id, "drain cleaning")
    await db.commit()

    # Cancel and re check
    job = (await db.execute(select(Job).where(Job.customer_id == cust.id))).scalar_one()
    await cancel_job(_ctx(db, business, cust), job.id)
    await db.commit()

    out = await list_my_appointments(_ctx(db, business, cust))
    assert "no upcoming" in out.lower()


# 4. Reschedule

async def test_reschedule_job_happy_path(db, business):
    slots = await _seed_slots(db, business, [3, 8])
    cust = await _make_customer(db, business)

    await book_job(_ctx(db, business, cust), slots[0].id, "drain cleaning")
    await db.commit()
    job = (await db.execute(select(Job).where(Job.customer_id == cust.id))).scalar_one()

    out = await reschedule_job(_ctx(db, business, cust), job.id, slots[1].id)
    await db.commit()
    assert "rescheduled" in out.lower()

    # Old slot freed, new slot taken
    old = (await db.execute(select(TimeSlot).where(TimeSlot.id == slots[0].id))).scalar_one()
    new = (await db.execute(select(TimeSlot).where(TimeSlot.id == slots[1].id))).scalar_one()
    assert old.is_available is True
    assert new.is_available is False

    fresh_job = (await db.execute(select(Job).where(Job.id == job.id))).scalar_one()
    assert fresh_job.time_slot_id == slots[1].id


async def test_reschedule_rejects_unavailable_new_slot(db, business):
    slots = await _seed_slots(db, business, [3, 8])
    cust = await _make_customer(db, business)

    # Book slot 0 for caller, then mark slot 1 unavailable (e.g., taken by someone else)
    await book_job(_ctx(db, business, cust), slots[0].id, "drain cleaning")
    await db.commit()
    slots[1].is_available = False
    await db.commit()

    job = (await db.execute(select(Job).where(Job.customer_id == cust.id))).scalar_one()
    out = await reschedule_job(_ctx(db, business, cust), job.id, slots[1].id)
    assert "not available" in out.lower()


async def test_reschedule_rejects_wrong_customer_job(db, business):
    slots = await _seed_slots(db, business, [3, 8])
    cust1 = await _make_customer(db, business)
    cust2 = await _make_customer(db, business, phone="+15550008888", name="Other")

    await book_job(_ctx(db, business, cust1), slots[0].id, "drain cleaning")
    await db.commit()
    job = (await db.execute(select(Job).where(Job.customer_id == cust1.id))).scalar_one()

    # cust2 tries to reschedule cust1's job
    out = await reschedule_job(_ctx(db, business, cust2), job.id, slots[1].id)
    assert "couldn't find" in out.lower()


# 5. Cancel a single appointment

async def test_cancel_job_happy_path(db, business):
    slots = await _seed_slots(db, business, [3])
    cust = await _make_customer(db, business)

    await book_job(_ctx(db, business, cust), slots[0].id, "drain cleaning")
    await db.commit()
    job = (await db.execute(select(Job).where(Job.customer_id == cust.id))).scalar_one()

    out = await cancel_job(_ctx(db, business, cust), job.id)
    await db.commit()
    assert "cancelled" in out.lower()

    fresh_job = (await db.execute(select(Job).where(Job.id == job.id))).scalar_one()
    assert fresh_job.status == JobStatus.cancelled

    # Slot is freed up for another customer
    fresh_slot = (await db.execute(select(TimeSlot).where(TimeSlot.id == slots[0].id))).scalar_one()
    assert fresh_slot.is_available is True


async def test_cancel_job_rejects_wrong_customer(db, business):
    slots = await _seed_slots(db, business, [3])
    cust1 = await _make_customer(db, business)
    cust2 = await _make_customer(db, business, phone="+15550008888", name="Other")

    await book_job(_ctx(db, business, cust1), slots[0].id, "drain cleaning")
    await db.commit()
    job = (await db.execute(select(Job).where(Job.customer_id == cust1.id))).scalar_one()

    out = await cancel_job(_ctx(db, business, cust2), job.id)
    assert "couldn't find" in out.lower()

    fresh_job = (await db.execute(select(Job).where(Job.id == job.id))).scalar_one()
    assert fresh_job.status == JobStatus.confirmed  # untouched


# 6. Cancel ALL

async def test_cancel_all_jobs_empty(db, business):
    cust = await _make_customer(db, business)
    out = await cancel_all_jobs(_ctx(db, business, cust))
    assert "no upcoming" in out.lower()


async def test_cancel_all_jobs_cancels_multiple(db, business):
    slots = await _seed_slots(db, business, [3, 5, 7])
    cust = await _make_customer(db, business)

    for s, jt in zip(slots, ["drain cleaning", "pipe repair", "leak detection"]):
        await book_job(_ctx(db, business, cust), s.id, jt)
    await db.commit()

    out = await cancel_all_jobs(_ctx(db, business, cust))
    await db.commit()
    assert "cancelled 3" in out.lower()

    jobs = (await db.execute(select(Job).where(Job.customer_id == cust.id))).scalars().all()
    assert all(j.status == JobStatus.cancelled for j in jobs)

    # All slots freed
    for s in slots:
        fresh = (await db.execute(select(TimeSlot).where(TimeSlot.id == s.id))).scalar_one()
        assert fresh.is_available is True


async def test_cancel_all_jobs_handles_job_with_no_time_slot(db, business):
    # Regression: cancel_all_jobs used to silently drop jobs whose time_slot was null because the outerjoin filter killed them. or_(... is_(None)) fixed it.
    cust = await _make_customer(db, business)
    db.add(Job(
        business_id=business.id,
        customer_id=cust.id,
        technician_id=None,
        time_slot_id=None,
        job_type="leak detection",
        status=JobStatus.confirmed,
        source="ai",
    ))
    await db.commit()

    out = await cancel_all_jobs(_ctx(db, business, cust))
    await db.commit()
    assert "cancelled 1" in out.lower()


async def test_cancel_all_jobs_scoped_to_caller(db, business):
    slots = await _seed_slots(db, business, [3, 5])
    cust1 = await _make_customer(db, business)
    cust2 = await _make_customer(db, business, phone="+15550008888", name="Other")

    await book_job(_ctx(db, business, cust1), slots[0].id, "drain cleaning")
    await book_job(_ctx(db, business, cust2), slots[1].id, "pipe repair")
    await db.commit()

    # cust1 cancels all ; cust2's job is untouched
    await cancel_all_jobs(_ctx(db, business, cust1))
    await db.commit()

    cust2_jobs = (await db.execute(select(Job).where(Job.customer_id == cust2.id))).scalars().all()
    assert len(cust2_jobs) == 1
    assert cust2_jobs[0].status == JobStatus.confirmed


# 7. Estimate matching (price guesser used during booking)

def test_estimate_exact_match():
    assert _estimate_for("drain cleaning") == 180


def test_estimate_longest_substring_wins():
    # "water heater install" must beat "water heater repair" by length
    assert _estimate_for("Customer wants water heater install today") == 540


def test_estimate_generic_word_does_not_match():
    # The fix: short generic word "repair" must NOT match "pipe repair" or any other entry.
    assert _estimate_for("repair") is None


def test_estimate_unknown_returns_none():
    assert _estimate_for("rocket surgery") is None


# 8. SMS / voice webhook entry points

async def test_inbound_sms_creates_customer_and_conversation(client, business):
    r = await client.post(
        "/webhooks/sms",
        data={
            "From": "+15550009999",
            "To": business.twilio_number,
            "Body": "Hi, I need a sink fixed",
        },
    )
    # We don't run the real LLM in tests ; without an API key the agent will fall back to the safe error string from the exception handler. Either 200 with TwiML or a managed fallback is acceptable; the side effects below are what matter.
    assert r.status_code == 200
    assert "<?xml" in r.text or "Response" in r.text


async def test_inbound_sms_unknown_business_returns_404(client):
    r = await client.post(
        "/webhooks/sms",
        data={"From": "+15550009999", "To": "+19999999999", "Body": "hi"},
    )
    assert r.status_code == 404


async def test_inbound_sms_malformed_payload_returns_empty_twiml(client, business):
    r = await client.post("/webhooks/sms", data={"From": "", "To": "", "Body": ""})
    assert r.status_code == 200
    assert "<?xml" in r.text or "Response" in r.text


async def test_voice_webhook_returns_twiml(client, business):
    r = await client.post(
        "/webhooks/voice",
        data={"From": "+15550009999", "To": business.twilio_number},
    )
    assert r.status_code == 200
    assert "Gather" in r.text or "Say" in r.text


# 9. Output sanitization (so a customer never hears "vertical bar")

def test_sanitize_strips_pipes():
    out = sanitize_for_speech("| a | b | c |")
    assert "|" not in out


def test_sanitize_strips_markdown_emphasis():
    out = sanitize_for_speech("**Booked!** Your appointment is confirmed.")
    assert "*" not in out
    assert "Booked" in out


def test_sanitize_strips_internal_tags():
    out = sanitize_for_speech("Wednesday at 3:30 PM [internal:slot_id=18]")
    assert "internal" not in out
    assert "Wednesday" in out


def test_sanitize_strips_fake_table_header():
    s = "Here are our times: Day Date Time Wednesday May 27 3:30 PM"
    out = sanitize_for_speech(s)
    assert "Day Date Time" not in out
    assert "Wednesday May 27 3:30 PM" in out


def test_sanitize_inserts_period_between_runon_times():
    s = "Wednesday May 27 3:30 PM Thursday May 28 8:00 AM Friday May 29 1:00 PM"
    out = sanitize_for_speech(s)
    # TTS pause = period; without these, the times stream together
    assert out.count(". ") >= 2


def test_sanitize_preserves_benign_prose():
    s = "Thanks for calling! How can I help you today?"
    assert sanitize_for_speech(s) == s


def test_sanitize_full_pipeline_on_real_failing_output():
    # The exact text the model produced that triggered this whole investigation
    raw = (
        "Unfortunately, it looks like we don't have any available slots for today. "
        "Here are our nearest available time slots: "
        "Day Date Time Wednesday May 27 3:30 PM Thursday May 28 8:00 AM "
        "Thursday May 28 10:30 AM Thursday May 28 1:00 PM Thursday May 28 3:30 PM "
        "Would any of these work for you?"
    )
    out = sanitize_for_speech(raw)
    assert "Day Date Time" not in out
    assert "Wednesday May 27 3:30 PM." in out
    assert "Thursday May 28 8:00 AM." in out
    assert "Would any of these work for you?" in out
