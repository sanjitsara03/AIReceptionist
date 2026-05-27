import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from twilio.rest import Client

from app.config import settings
from app.database import get_db
from app.events import publish
from app.models import Business, Conversation, Customer, MessageDirection
from app.schemas import ConversationResponse, MessageCreate, MessageResponse
from app.auth import get_current_business_id
from app.services.conversation import save_message

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Module level Twilio client ; same pattern as app/scheduler.py. The SDK is sync, so individual calls are wrapped in asyncio.to_thread so we don't block the event loop while waiting on Twilio.
twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

# Twilio SMS max body length is 1600 chars; we cap a little tighter to encourage concise replies and avoid surprising multi part charges.
MAX_REPLY_LENGTH = 1000


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    result = await db.execute(
        select(Conversation)
        .join(Conversation.customer)
        .where(Customer.business_id == business_id)
        .options(
            selectinload(Conversation.customer).selectinload(Customer.jobs),
            selectinload(Conversation.messages),
        )
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .join(Conversation.customer)
        .where(Conversation.id == conversation_id, Customer.business_id == business_id)
        .options(
            selectinload(Conversation.customer).selectinload(Customer.jobs),
            selectinload(Conversation.messages),
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
async def send_owner_reply(
    conversation_id: int,
    payload: MessageCreate,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Send an SMS from the business owner to the customer in this conversation.

    Replies are SMS-only — voice conversations are read-only because we can't
    place a real outbound voice call from a button click (and a recording would
    arrive out of context). The message is sent via Twilio first, then persisted;
    if Twilio fails we surface the error and never write a fake outbound row.
    """
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Message body cannot be empty.")
    if len(body) > MAX_REPLY_LENGTH:
        raise HTTPException(status_code=422, detail=f"Message too long (max {MAX_REPLY_LENGTH} chars).")

    # Pull the conversation with its customer + the business in one round trip.
    result = await db.execute(
        select(Conversation)
        .join(Conversation.customer)
        .where(Conversation.id == conversation_id, Customer.business_id == business_id)
        .options(selectinload(Conversation.customer))
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        # Either it doesn't exist or it belongs to a different business ; same 404 either way so we don't leak cross tenant existence.
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.channel != "sms":
        raise HTTPException(status_code=400, detail="Owner replies are only supported for SMS conversations.")

    biz_result = await db.execute(select(Business).where(Business.id == business_id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found.")

    # Send via Twilio first ; if this throws, we don't want a phantom outbound row sitting in the DB making it look like the customer was contacted.
    try:
        await asyncio.to_thread(
            twilio_client.messages.create,
            body=body,
            from_=business.twilio_number,
            to=conversation.customer.phone,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SMS provider error: {e}")

    message = await save_message(db, conversation.id, MessageDirection.outbound, body)
    await db.commit()
    await db.refresh(message)

    # Live update any open dashboard tabs for this business.
    publish(business_id, "conversation.updated", {"conversation_id": conversation.id})

    return message
