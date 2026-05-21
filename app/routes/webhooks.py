from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.twiml.messaging_response import MessagingResponse

from app.database import get_db
from app.models import MessageDirection
from app.agent.claude import get_ai_reply
from app.agent.conversation import (
    get_or_create_customer,
    get_or_create_conversation,
    load_history,
    save_message,
)

router = APIRouter()

BUSINESS_ID = 1  # hardcoded for now 


@router.post("/webhooks/sms")
async def inbound_sms(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()

    from_number = form.get("From")
    body = form.get("Body")

    # Get or create customer and conversation
    customer = await get_or_create_customer(db, BUSINESS_ID, from_number)
    conversation = await get_or_create_conversation(db, customer)

    # Save inbound message
    await save_message(db, conversation, MessageDirection.inbound, body)

    # Load full history and get AI reply
    history = await load_history(db, conversation)
    reply = await get_ai_reply(history)

    # Save outbound message
    await save_message(db, conversation, MessageDirection.outbound, reply)

    await db.commit()

    response = MessagingResponse()
    response.message(reply)

    return Response(content=str(response), media_type="application/xml")
