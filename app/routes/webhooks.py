from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather

from app.database import get_db
from app.events import publish
from app.models import Business, MessageDirection
from app.agent.agent import get_ai_reply
from app.agent.tools import AgentDeps
from app.services.conversation import (
    get_or_create_customer,
    get_or_create_conversation,
    load_history,
    save_message,
)

router = APIRouter()

VOICE_GREETING = "Hi! You've reached our AI receptionist. How can I help you today?"


def strip_emojis(text: str) -> str:
    return text.encode("ascii", "ignore").decode("ascii")


@router.post("/webhooks/sms")
async def inbound_sms(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()

    from_number = form.get("From")
    to_number = form.get("To")
    body = form.get("Body")

    # Twilio occasionally posts malformed/test payloads — bail early.
    if not from_number or not to_number or not body:
        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # Look up business by Twilio number
    result = await db.execute(select(Business).where(Business.twilio_number == to_number))
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail="Business not found for this number")

    # Get or create customer and conversation (this handler is SMS-only)
    customer = await get_or_create_customer(db, business.id, from_number)
    conversation = await get_or_create_conversation(db, customer, channel="sms")

    # Save inbound message
    await save_message(db, conversation, MessageDirection.inbound, body)

    # Load full history and get AI reply
    history = await load_history(db, conversation)
    deps = AgentDeps(db=db, business_id=business.id, business=business, customer=customer)
    reply = await get_ai_reply(history, deps)

    # Save outbound message
    await save_message(db, conversation, MessageDirection.outbound, reply)

    await db.commit()

    # Notify any connected dashboard for this business
    publish(business.id, "conversation.updated", {"conversation_id": conversation.id})

    response = MessagingResponse()
    response.message(reply)

    return Response(content=str(response), media_type="application/xml")


@router.post("/webhooks/voice")
async def inbound_call(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    to_number = form.get("To")

    # Look up the business so we can use its custom greeting
    greeting = VOICE_GREETING
    if to_number:
        result = await db.execute(select(Business).where(Business.twilio_number == to_number))
        business = result.scalar_one_or_none()
        if business and business.voice_greeting and business.voice_greeting.strip():
            greeting = business.voice_greeting

    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/webhooks/voice/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.say(greeting, voice="Polly.Joanna")
    response.append(gather)
    return Response(content=str(response), media_type="application/xml")


@router.post("/webhooks/voice/respond")
async def voice_respond(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()

    from_number = form.get("From")
    to_number = form.get("To")
    speech_result = form.get("SpeechResult", "")

    response = VoiceResponse()

    # Reject malformed payloads early
    if not from_number or not to_number:
        response.say("Sorry, something went wrong. Goodbye.", voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # If the caller said nothing, prompt again rather than hitting the agent with empty input
    if not speech_result.strip():
        gather = Gather(
            input="speech",
            action="/webhooks/voice/respond",
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        gather.say("Sorry, I didn't catch that. Could you repeat?", voice="Polly.Joanna")
        response.append(gather)
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # Look up business by Twilio number
    result = await db.execute(select(Business).where(Business.twilio_number == to_number))
    business = result.scalar_one_or_none()

    if not business:
        response.say("Sorry, we could not find your business. Goodbye.", voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # Get or create customer and conversation (this handler is voice-only)
    customer = await get_or_create_customer(db, business.id, from_number)
    conversation = await get_or_create_conversation(db, customer, channel="voice")

    # Save what the customer said
    await save_message(db, conversation, MessageDirection.inbound, speech_result)

    # Get AI reply
    history = await load_history(db, conversation)
    deps = AgentDeps(db=db, business_id=business.id, business=business, customer=customer)
    reply = await get_ai_reply(history, deps)

    # Save AI reply
    await save_message(db, conversation, MessageDirection.outbound, reply)
    await db.commit()

    publish(business.id, "conversation.updated", {"conversation_id": conversation.id})

    # Speak the reply and listen again
    gather = Gather(
        input="speech",
        action="/webhooks/voice/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.say(strip_emojis(reply), voice="Polly.Joanna")
    response.append(gather)

    # If customer doesn't say anything, hang up politely
    response.say("We didn't hear anything. Goodbye!", voice="Polly.Joanna")

    return Response(content=str(response), media_type="application/xml")
