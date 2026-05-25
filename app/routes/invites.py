import secrets
from datetime import timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.limiter import limiter
from app.models import Invite, Business
from app.schemas import InviteResponse
from app.config import settings
from app.models import utcnow

router = APIRouter(prefix="/invites", tags=["invites"])


def _require_admin(x_admin_secret: str = Header(...)):
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret.")


@router.post("", response_model=InviteResponse, dependencies=[Depends(_require_admin)])
async def create_invite(business_id: int, expires_in_days: int = 7, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Business).where(Business.id == business_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found.")

    invite = Invite(
        token=secrets.token_urlsafe(32),
        business_id=business_id,
        expires_at=utcnow() + timedelta(days=expires_in_days),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    return InviteResponse(
        token=invite.token,
        business_name=business.name,
        expires_at=invite.expires_at,
        claimed=False,
    )


@router.get("/{token}", response_model=InviteResponse)
@limiter.limit("20/minute")
async def get_invite(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Invite).where(Invite.token == token).options()
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found.")

    now = utcnow()
    if invite.expires_at < now:
        raise HTTPException(status_code=410, detail="Invite has expired.")

    result = await db.execute(select(Business).where(Business.id == invite.business_id))
    business = result.scalar_one_or_none()

    return InviteResponse(
        token=invite.token,
        business_name=business.name,
        expires_at=invite.expires_at,
        claimed=invite.claimed_at is not None,
    )
