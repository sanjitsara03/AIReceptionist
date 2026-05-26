from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Business
from app.auth import _decode_token
from app.events import subscribe

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def stream(
    token: str = Query(..., description="Auth0 access token (query param because EventSource can't send headers)"),
    db: AsyncSession = Depends(get_db),
):
    """Server-Sent Events stream for the authenticated user's business."""
    payload = await _decode_token(token)
    auth0_id = payload.get("sub", "")

    result = await db.execute(select(Business).where(Business.owner_auth0_id == auth0_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=403, detail="No business associated with this account.")

    return StreamingResponse(
        subscribe(business.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable proxy buffering
        },
    )
