"""
Seed script for Joe's Plumbing demo data.

Run:  .venv/bin/python seed.py
Wipe: set WIPE=1 to drop existing data first, e.g. WIPE=1 .venv/bin/python seed.py
"""

import asyncio
import os
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.models import (
    Business, Technician, Customer, TimeSlot, Job, JobStatus,
    Conversation, Message, MessageDirection,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PDT = timezone(timedelta(hours=-7))   # LA in summer
TODAY = date.today()


def pdt(day_offset: int, hour: int, minute: int = 0) -> datetime:
    """Return a timezone-aware datetime in LA time."""
    d = TODAY + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=PDT)


# day_offset shortcuts
YESTERDAY = -1
TODAY_O = 0
TOMORROW = 1


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

async def seed():
    async with AsyncSessionLocal() as db:

        if os.getenv("WIPE"):
            await db.execute(text(
                "TRUNCATE invites, messages, conversations, jobs, time_slots, "
                "customers, technicians, businesses RESTART IDENTITY CASCADE"
            ))
            await db.commit()
            print("Wiped all tables and reset sequences.")

        # ------------------------------------------------------------------ #
        # Business
        # ------------------------------------------------------------------ #
        business = Business(
            name="Joe's Plumbing",
            twilio_number="+18055905679",
            services=(
                "Drain cleaning, pipe repair, water heater installation and repair, "
                "leak detection, emergency plumbing, bathroom and kitchen plumbing, "
                "sewer line inspection, garbage disposal repair."
            ),
            hours="Mon–Fri 7:00 AM – 6:00 PM · Sat 8:00 AM – 2:00 PM · Sun closed",
            address="123 Main Street, Los Angeles, CA 90001",
        )
        db.add(business)
        await db.flush()

        # ------------------------------------------------------------------ #
        # Technicians
        # ------------------------------------------------------------------ #
        joe  = Technician(business_id=business.id, name="Joe Smith",    phone="+15550000002", active=True)
        mike = Technician(business_id=business.id, name="Mike Johnson", phone="+15550000003", active=True)
        dave = Technician(business_id=business.id, name="Dave Lee",     phone="+15550000004", active=True)
        db.add_all([joe, mike, dave])
        await db.flush()

        # ------------------------------------------------------------------ #
        # Customers
        # ------------------------------------------------------------------ #
        maria   = Customer(business_id=business.id, name="Maria Alvarez",   phone="+13105550142")
        david   = Customer(business_id=business.id, name="David Park",      phone="+13235550178")
        linda   = Customer(business_id=business.id, name="Linda Cho",       phone="+18185550193")
        brett   = Customer(business_id=business.id, name="Brett Henderson", phone="+14245550166")
        aisha   = Customer(business_id=business.id, name="Aisha Mahmood",   phone="+15625550121")
        tomas   = Customer(business_id=business.id, name="Tomás Vega",      phone="+12135550188")
        hannah  = Customer(business_id=business.id, name="Hannah Weiss",    phone="+13105550119")
        ravi    = Customer(business_id=business.id, name="Ravi Patel",      phone="+13105550104")
        sarah   = Customer(business_id=business.id, name="Sarah Donnelly",  phone="+12135550151")
        unknown = Customer(business_id=business.id, name="Unknown",         phone="+18185550177")

        db.add_all([maria, david, linda, brett, aisha, tomas, hannah, ravi, sarah, unknown])
        await db.flush()

        # ------------------------------------------------------------------ #
        # Time slots + Jobs
        # We create a slot, flush to get its ID, then attach a job to it.
        # ------------------------------------------------------------------ #

        async def make_job(
            customer, tech, job_type, status, source, estimate,
            day_offset, start_h, start_m, end_h, end_m,
            notes=None, reminder_sent=False,
        ):
            slot = TimeSlot(
                technician_id=tech.id,
                start_time=pdt(day_offset, start_h, start_m),
                end_time=pdt(day_offset, end_h, end_m),
                is_available=False,
            )
            db.add(slot)
            await db.flush()
            job = Job(
                business_id=business.id,
                customer_id=customer.id,
                technician_id=tech.id,
                time_slot_id=slot.id,
                job_type=job_type,
                status=status,
                source=source,
                estimate=estimate,
                notes=notes,
                reminder_sent=reminder_sent,
            )
            db.add(job)
            await db.flush()
            return job

        # --- Yesterday ---
        await make_job(brett,  joe,  "Drain cleaning",       JobStatus.no_show,   "ai",    180, YESTERDAY,  10, 0,  11, 0)
        await make_job(maria,  mike, "Pipe repair",          JobStatus.completed, "ai",    380, YESTERDAY,  13, 0,  15, 0)
        await make_job(sarah,  dave, "Water heater repair",  JobStatus.completed, "ai",    320, YESTERDAY,   8, 0,  10, 0)
        await make_job(david,  joe,  "Bathroom plumbing",    JobStatus.cancelled, "ai",    380, YESTERDAY,  11, 0,  13, 0)

        # --- Today ---
        await make_job(brett,  joe,  "Water heater repair",  JobStatus.in_progress, "ai",  320, TODAY_O,  8,  0,  10, 0,  reminder_sent=True)
        await make_job(maria,  mike, "Drain cleaning",       JobStatus.completed,   "ai",  180, TODAY_O,  9,  0,  10, 0,  reminder_sent=True)
        await make_job(ravi,   dave, "Leak detection",       JobStatus.confirmed,   "ai",  220, TODAY_O,  10, 30, 12, 0,  reminder_sent=True)
        await make_job(linda,  joe,  "Pipe repair",          JobStatus.confirmed,   "human", 410, TODAY_O, 11, 0,  13, 0,  reminder_sent=True)
        await make_job(david,  mike, "Bathroom plumbing",    JobStatus.confirmed,   "ai",  380, TODAY_O,  13, 0,  15, 0)
        await make_job(sarah,  dave, "Emergency clog",       JobStatus.confirmed,   "ai",  245, TODAY_O,  13, 30, 15, 0)
        await make_job(tomas,  joe,  "Kitchen sink install", JobStatus.confirmed,   "ai",  290, TODAY_O,  15, 30, 17, 0)
        await make_job(aisha,  mike, "Water heater install", JobStatus.pending,     "ai",  540, TODAY_O,  16, 0,  18, 0)

        # --- Tomorrow ---
        await make_job(hannah, joe,  "Drain cleaning",       JobStatus.confirmed,   "ai",  180, TOMORROW, 9,  0,  10, 30)
        await make_job(unknown, dave, "Leak detection",      JobStatus.pending,     "ai",  220, TOMORROW, 11, 0,  12, 30)

        # --- Future available slots (for booking) ---
        for day_offset in range(2, 8):
            for tech in [joe, mike, dave]:
                for (sh, sm, eh, em) in [(8, 0, 10, 0), (10, 30, 12, 30), (13, 0, 15, 0), (15, 30, 17, 30)]:
                    slot = TimeSlot(
                        technician_id=tech.id,
                        start_time=pdt(day_offset, sh, sm),
                        end_time=pdt(day_offset, eh, em),
                        is_available=True,
                    )
                    db.add(slot)

        await db.flush()

        # ------------------------------------------------------------------ #
        # Conversations + Messages
        # ------------------------------------------------------------------ #

        async def convo(customer, channel, day_offset, hour, minute, messages):
            """Create a conversation with a sequence of messages."""
            c = Conversation(
                customer_id=customer.id,
                channel=channel,
            )
            c.created_at = pdt(day_offset, hour, minute)
            c.updated_at = pdt(day_offset, hour, minute)
            db.add(c)
            await db.flush()

            last_ts = pdt(day_offset, hour, minute)
            for i, (direction, body) in enumerate(messages):
                last_ts = last_ts + timedelta(minutes=i + 1)
                msg = Message(
                    conversation_id=c.id,
                    direction=direction,
                    body=body,
                )
                msg.created_at = last_ts
                msg.updated_at = last_ts
                db.add(msg)

            c.updated_at = last_ts
            await db.flush()
            return c

        IN = MessageDirection.inbound
        OUT = MessageDirection.outbound

        # 1 — Unknown caller, voice, today, no booking
        await convo(unknown, "voice", TODAY_O, 11, 42, [
            (IN,  "Hi, my kitchen sink is leaking everywhere and there's water all over the floor."),
            (OUT, "I'm sorry to hear that. I can get someone out today. Can I get your name and the address?"),
            (IN,  "Yeah it's bad. Address is 4421 Atwater Ave."),
            (OUT, "Got it. Let me check who's available."),
            (OUT, "I have Dave at 2:30 PM today, or Joe at 4 PM. Which works better?"),
            (IN,  "Let me call my husband and call back."),
            (OUT, "Of course. Call back any time at this number and I'll have your info ready."),
        ])

        # 2 — Aisha Mahmood, SMS, today, booked water heater install
        await convo(aisha, "sms", TODAY_O, 10, 18, [
            (IN,  "Hey, my water heater is making a weird humming noise. Can someone take a look today?"),
            (OUT, "Hi! That usually means sediment buildup, sometimes a failing element. I can send a tech out today. What's your address?"),
            (IN,  "812 La Brea Ave Apt 4"),
            (OUT, "Let me check availability for you."),
            (OUT, "I have Mike at 1 PM or 4 PM today. Either work?"),
            (IN,  "4pm works"),
            (OUT, "Booked! Mike Johnson will be there today at 4:00 PM. Estimate is $540. Reply STOP to opt out of texts."),
            (IN,  "Great thanks"),
        ])

        # 3 — Sarah Donnelly, voice, today, booked emergency clog
        await convo(sarah, "voice", TODAY_O, 9, 4, [
            (IN,  "Hi this is Sarah Donnelly, my toilet is overflowing."),
            (OUT, "Sarah, I'm sorry. Let's get you on the schedule right away. Same address as last time on Echo Park?"),
            (IN,  "Yes same address."),
            (OUT, "Got it. Checking Dave's schedule."),
            (OUT, "Dave can be there at 1:30 PM today. Does that work?"),
            (IN,  "Yes please."),
            (OUT, "Booked! Dave Lee will be there today at 1:30 PM. You'll get a text reminder an hour before. Estimate is $245."),
        ])

        # 4 — Hannah Weiss, SMS, yesterday, booked drain cleaning tomorrow
        await convo(hannah, "sms", YESTERDAY, 18, 32, [
            (IN,  "Bathroom sink draining super slow"),
            (OUT, "Hi! Sounds like buildup in the trap or pipe. I can schedule a drain cleaning. Any preference on time?"),
            (IN,  "Tomorrow morning if possible"),
            (OUT, "Joe can come tomorrow at 9 AM. Estimate is $180. Want me to book it?"),
            (IN,  "yes pls"),
            (OUT, "Booked! Joe Smith will be there tomorrow at 9:00 AM. We'll text a reminder in the morning."),
        ])

        # 5 — David Park, SMS, yesterday, just shopping around
        await convo(david, "sms", YESTERDAY, 14, 11, [
            (IN,  "How much for a water heater replacement, 40 gallon?"),
            (OUT, "For a standard 40-gallon tank install, we typically quote $540 plus the cost of the unit. We'd send a tech for a quick on-site quote first. Want to schedule that?"),
            (IN,  "Just shopping around, thanks"),
            (OUT, "Sounds good. Call or text any time if you decide to go ahead."),
        ])

        # 6 — Linda Cho, SMS, yesterday, rescheduled pipe repair to today
        await convo(linda, "sms", YESTERDAY, 11, 2, [
            (IN,  "I need to move my Saturday appointment"),
            (OUT, "Of course. Which appointment, and when would you like to move it to?"),
            (IN,  "The pipe repair, can we do Monday morning?"),
            (OUT, "I have Joe at 11 AM Monday. Want me to move it there?"),
            (IN,  "yes thanks"),
            (OUT, "Rescheduled! Joe Smith will be there Monday at 11:00 AM for the pipe repair."),
        ])

        # 7 — Tomás Vega, voice, yesterday, booked kitchen sink install
        await convo(tomas, "voice", YESTERDAY, 9, 21, [
            (IN,  "I just got a new sink and I need it installed."),
            (OUT, "Great, we can do that. Did you get a new faucet too, or just the sink?"),
            (IN,  "New sink and new faucet."),
            (OUT, "Perfect. Let me check today's schedule."),
            (OUT, "I have Joe at 3:30 PM today. Want me to book that?"),
            (IN,  "Yeah that's good."),
            (OUT, "Booked! Joe Smith will be there today at 3:30 PM for the kitchen sink and faucet install. Estimate is $290."),
        ])

        # 8 — Ravi Patel, SMS, today, booked leak detection
        await convo(ravi, "sms", TODAY_O, 8, 45, [
            (IN,  "There's a damp spot on my ceiling and I think there's a pipe leaking above it"),
            (OUT, "That needs to get looked at quickly — could be a slow drip that gets worse. I can send Dave out this morning for a leak detection. Does 10:30 AM work?"),
            (IN,  "That's perfect"),
            (OUT, "Booked! Dave Lee will be there at 10:30 AM today. Estimate is $220. We'll text 30 min before he heads over."),
        ])

        await db.commit()

        # Summary
        print(
            f"Seeded:\n"
            f"  1 business ({business.name})\n"
            f"  3 technicians\n"
            f"  10 customers\n"
            f"  14 jobs (4 yesterday · 8 today · 2 tomorrow)\n"
            f"  8 conversations with full message threads\n"
            f"  84 future available time slots"
        )


if __name__ == "__main__":
    asyncio.run(seed())
