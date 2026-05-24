import asyncio
from datetime import datetime, timezone, timedelta
from app.database import AsyncSessionLocal
from app.models import Business, Technician, TimeSlot


async def seed():
    async with AsyncSessionLocal() as session:
        # 1 Business
        business = Business(
            name="Joe's Plumbing",
            twilio_number="+18055905679",
            services="Drain cleaning, pipe repair, water heater installation and repair, leak detection, emergency plumbing, bathroom and kitchen plumbing.",
            hours="Monday to Friday 7am to 6pm, Saturday 8am to 2pm. Closed Sunday.",
            address="123 Main Street, Los Angeles, CA 90001",
        )
        session.add(business)
        await session.flush()

        # 3 Technicians
        technicians = [
            Technician(business_id=business.id, name="Joe Smith", phone="+15550000002"),
            Technician(business_id=business.id, name="Mike Johnson", phone="+15550000003"),
            Technician(business_id=business.id, name="Dave Lee", phone="+15550000004"),
        ]
        session.add_all(technicians)
        await session.flush()

        # 30 time slots — 2 slots per technician per day for the next 10 days
        slots = []
        base = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)

        for i in range(10):
            day = base + timedelta(days=i + 1)
            for tech in technicians:
                # Morning slot
                slots.append(TimeSlot(
                    technician_id=tech.id,
                    start_time=day,
                    end_time=day + timedelta(hours=2),
                ))
                # Afternoon slot
                slots.append(TimeSlot(
                    technician_id=tech.id,
                    start_time=day + timedelta(hours=4),
                    end_time=day + timedelta(hours=6),
                ))

        session.add_all(slots)
        await session.commit()

        print(f"Seeded: 1 business, {len(technicians)} technicians, {len(slots)} time slots")


if __name__ == "__main__":
    asyncio.run(seed())
