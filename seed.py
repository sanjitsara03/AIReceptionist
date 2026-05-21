import asyncio
from datetime import datetime, timezone, timedelta
from app.database import AsyncSessionLocal
from app.models import Business, Technician, TimeSlot


async def seed():
    async with AsyncSessionLocal() as session:
        # 1 Business
        business = Business(
            name="Joe's Plumbing",
            twilio_number="+15550000001",
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

        # 10 Time Slots spread across the next 5 days, 2 per technician
        slots = []
        base = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
        for i in range(5):
            day = base + timedelta(days=i + 1)
            slots.append(TimeSlot(
                technician_id=technicians[0].id,
                start_time=day,
                end_time=day + timedelta(hours=2),
            ))
            slots.append(TimeSlot(
                technician_id=technicians[1].id,
                start_time=day + timedelta(hours=3),
                end_time=day + timedelta(hours=5),
            ))

        session.add_all(slots)
        await session.commit()

        print(f"Seeded: 1 business, {len(technicians)} technicians, {len(slots)} time slots")


if __name__ == "__main__":
    asyncio.run(seed())
