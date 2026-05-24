from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Customer
from app.schemas import CustomerResponse

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerResponse])
async def list_customers(business_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Customer)
        .where(Customer.business_id == business_id)
        .order_by(Customer.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: int, business_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Customer)
        .where(Customer.id == customer_id, Customer.business_id == business_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return customer
