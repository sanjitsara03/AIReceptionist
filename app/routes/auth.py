from datetime import timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.limiter import limiter
from app.models import Business, Invite
from app.auth import get_current_auth0_id
from app.schemas import BusinessResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=BusinessResponse | None)
async def get_me(
    auth0_id: str = Depends(get_current_auth0_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Business).where(Business.owner_auth0_id == auth0_id)
    )
    return result.scalar_one_or_none()


@router.post("/claim", response_model=BusinessResponse)
@limiter.limit("10/minute")
async def claim_business(
    request: Request,
    invite_token: str,
    auth0_id: str = Depends(get_current_auth0_id),
    db: AsyncSession = Depends(get_db),
):
    # Already linked?
    existing = await db.execute(
        select(Business).where(Business.owner_auth0_id == auth0_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Account already linked to a business.")

    # Validate invite
    invite_result = await db.execute(
        select(Invite).where(Invite.token == invite_token)
    )
    invite = invite_result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found.")
    if invite.claimed_at is not None:
        raise HTTPException(status_code=410, detail="Invite has already been used.")
    from datetime import datetime
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invite has expired.")

    # Link business to this user
    biz_result = await db.execute(
        select(Business).where(Business.id == invite.business_id)
    )
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found.")

    from datetime import datetime
    business.owner_auth0_id = auth0_id
    invite.claimed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(business)
    return business
