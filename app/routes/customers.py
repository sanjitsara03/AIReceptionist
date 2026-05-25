from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Customer
from app.schemas import CustomerResponse
from app.auth import get_current_business_id

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerResponse])
async def list_customers(
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Search by name or phone"),
):
    stmt = (
        select(Customer)
        .where(Customer.business_id == business_id)
        .options(selectinload(Customer.jobs))
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    stmt = stmt.order_by(Customer.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Customer)
        .where(Customer.id == customer_id, Customer.business_id == business_id)
        .options(selectinload(Customer.jobs))
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return customer
