"""
Platform-admin endpoints — protected by X-Admin-Secret header.

Used by the /admin frontend route to onboard new businesses without needing
to touch the database directly or curl invite endpoints by hand.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import Business, Customer, Job, TimeSlot, Technician, Conversation, Message, Invite
from app.schemas import BusinessCreate, BusinessAdminResponse, InviteResponse
from app.routes.invites import _require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(_require_admin)])


def _to_admin_response(b: Business, customer_count: int, job_count: int, conversation_count: int) -> BusinessAdminResponse:
    return BusinessAdminResponse(
        id=b.id,
        name=b.name,
        twilio_number=b.twilio_number,
        services=b.services,
        hours=b.hours,
        address=b.address,
        voice_greeting=b.voice_greeting,
        system_prompt=b.system_prompt,
        owner_auth0_id=b.owner_auth0_id,
        created_at=b.created_at,
        customer_count=customer_count,
        job_count=job_count,
        conversation_count=conversation_count,
    )


@router.get("/businesses", response_model=list[BusinessAdminResponse])
async def list_businesses(db: AsyncSession = Depends(get_db)):
    """List every business on the platform with per-business counts."""
    result = await db.execute(select(Business).order_by(Business.id.asc()))
    businesses = result.scalars().all()

    out: list[BusinessAdminResponse] = []
    for b in businesses:
        customer_count = (await db.execute(
            select(func.count(Customer.id)).where(Customer.business_id == b.id)
        )).scalar() or 0
        job_count = (await db.execute(
            select(func.count(Job.id)).where(Job.business_id == b.id)
        )).scalar() or 0
        conversation_count = (await db.execute(
            select(func.count(Conversation.id))
            .join(Customer, Conversation.customer_id == Customer.id)
            .where(Customer.business_id == b.id)
        )).scalar() or 0
        out.append(_to_admin_response(b, customer_count, job_count, conversation_count))
    return out


@router.post("/businesses", response_model=BusinessAdminResponse, status_code=201)
async def create_business(payload: BusinessCreate, db: AsyncSession = Depends(get_db)):
    """Create a new business. Twilio number must be unique."""
    business = Business(**payload.model_dump())
    db.add(business)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"twilio_number {payload.twilio_number!r} is already in use by another business.",
        )
    await db.refresh(business)
    # Brand new, so all counts are zero.
    return _to_admin_response(business, 0, 0, 0)


@router.delete("/businesses/{business_id}", status_code=204)
async def delete_business(business_id: int, db: AsyncSession = Depends(get_db)):
    """
    Delete a business and all of its data. Postgres FK cascade isn't set up
    across all relationships, so we delete in dependency order inside a
    single transaction.
    """
    biz = (await db.execute(select(Business).where(Business.id == business_id))).scalar_one_or_none()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    # Order matters ; children before parents. messages -> conversations -> jobs -> time_slots -> invites -> customers -> technicians -> business
    await db.execute(delete(Message).where(Message.conversation_id.in_(
        select(Conversation.id)
        .join(Customer, Conversation.customer_id == Customer.id)
        .where(Customer.business_id == business_id)
    )))
    await db.execute(delete(Conversation).where(Conversation.customer_id.in_(
        select(Customer.id).where(Customer.business_id == business_id)
    )))
    await db.execute(delete(Job).where(Job.business_id == business_id))
    await db.execute(delete(TimeSlot).where(TimeSlot.technician_id.in_(
        select(Technician.id).where(Technician.business_id == business_id)
    )))
    await db.execute(delete(Invite).where(Invite.business_id == business_id))
    await db.execute(delete(Customer).where(Customer.business_id == business_id))
    await db.execute(delete(Technician).where(Technician.business_id == business_id))
    await db.delete(biz)
    await db.commit()


@router.get("/invites", response_model=list[InviteResponse])
async def list_invites_for_business(
    business_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """List all invites for a specific business (claimed + unclaimed + expired)."""
    biz = (await db.execute(select(Business).where(Business.id == business_id))).scalar_one_or_none()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    result = await db.execute(
        select(Invite)
        .where(Invite.business_id == business_id)
        .order_by(Invite.created_at.desc())
    )
    invites = result.scalars().all()
    return [
        InviteResponse(
            token=inv.token,
            business_name=biz.name,
            expires_at=inv.expires_at,
            claimed=inv.claimed_at is not None,
        )
        for inv in invites
    ]
