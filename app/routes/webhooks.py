from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather

from app.config import settings
from app.database import get_db
from app.events import publish
from app.limiter import limiter
from app.models import Business, Customer, Message, Conversation, MessageDirection
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
LIMIT_REACHED_REPLY = (
    "Sorry, this number has reached its daily message limit. "
    "Please try again tomorrow or call directly."
)


# ---------------------------------------------------------------------------
# Twilio request signature validation
# ---------------------------------------------------------------------------
#
# Twilio signs every webhook POST with HMAC-SHA1 over the full URL + the
# url-encoded form body, using our account's TWILIO_AUTH_TOKEN as the key.
# Without this check, anyone can hit /webhooks/* with fake POSTs and burn
# unlimited Claude API tokens. This is the single most important production
# guard for cost control.

def _candidate_urls(request: Request) -> list[str]:
    """
    Build the list of URLs to try matching the Twilio signature against.

    Twilio's HMAC is over the EXACT URL it called — usually the one configured
    in the Twilio console. Behind Railway's proxy we can't always reconstruct
    that string byte-for-byte, so we try a few variations:

      1. settings.webhook_base_url + path (the explicit, recommended source)
      2. https + X-Forwarded-Host + path (Railway-typical)
      3. X-Forwarded-Proto + X-Forwarded-Host + path
      4. The raw request.url (works locally, rarely in prod)

    First match wins. As long as ONE matches, the request is authentic.
    """
    path = request.url.path
    qs = f"?{request.url.query}" if request.url.query else ""

    fwd_host = (request.headers.get("X-Forwarded-Host") or request.url.netloc).split(",")[0].strip()
    fwd_proto = (request.headers.get("X-Forwarded-Proto") or request.url.scheme).split(",")[0].strip()

    candidates: list[str] = []
    if settings.webhook_base_url:
        base = settings.webhook_base_url.rstrip("/")
        candidates.append(f"{base}{path}{qs}")
    candidates.append(f"https://{fwd_host}{path}{qs}")
    candidates.append(f"{fwd_proto}://{fwd_host}{path}{qs}")
    candidates.append(str(request.url))

    # De-dupe while preserving order
    seen, unique = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


async def verify_twilio_signature(request: Request) -> None:
    if not settings.validate_twilio_signature:
        return  # disabled in tests / temp override

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Twilio signature.")

    form = await request.form()
    form_dict = {k: v for k, v in form.items()}

    validator = RequestValidator(settings.twilio_auth_token)
    for url in _candidate_urls(request):
        if validator.validate(url, form_dict, signature):
            return

    # Log enough context to diagnose mismatches without leaking the auth token.
    import logging
    logging.getLogger("twilio.signature").warning(
        "Twilio signature mismatch. tried=%s host=%s fwd_host=%s fwd_proto=%s",
        _candidate_urls(request),
        request.url.netloc,
        request.headers.get("X-Forwarded-Host"),
        request.headers.get("X-Forwarded-Proto"),
    )
    raise HTTPException(status_code=403, detail="Invalid Twilio signature.")


# ---------------------------------------------------------------------------
# Per-business daily message cap
# ---------------------------------------------------------------------------

async def _over_daily_cap(db: AsyncSession, business_id: int) -> bool:
    cap = settings.daily_message_limit_per_business
    if cap <= 0:
        return False
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    result = await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .join(Customer, Customer.id == Conversation.customer_id)
        .where(
            Customer.business_id == business_id,
            Message.direction == MessageDirection.inbound,
            Message.created_at >= since,
        )
    )
    return (result.scalar() or 0) >= cap


def strip_emojis(text: str) -> str:
    return text.encode("ascii", "ignore").decode("ascii")


# ---------------------------------------------------------------------------
# SMS webhook
# ---------------------------------------------------------------------------

@router.post("/webhooks/sms", dependencies=[Depends(verify_twilio_signature)])
@limiter.limit("60/minute")
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

    # Persist the inbound message in its own transaction so an agent crash can't lose it.
    await save_message(db, conversation, MessageDirection.inbound, body)
    await db.commit()

    # Hard daily cap per business — skip the LLM if exceeded.
    if await _over_daily_cap(db, business.id):
        await save_message(db, conversation, MessageDirection.outbound, LIMIT_REACHED_REPLY)
        await db.commit()
        publish(business.id, "conversation.updated", {"conversation_id": conversation.id})
        response = MessagingResponse()
        response.message(LIMIT_REACHED_REPLY)
        return Response(content=str(response), media_type="application/xml")

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


# ---------------------------------------------------------------------------
# Voice webhook — initial greeting
# ---------------------------------------------------------------------------

@router.post("/webhooks/voice", dependencies=[Depends(verify_twilio_signature)])
@limiter.limit("60/minute")
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


# ---------------------------------------------------------------------------
# Voice webhook — each speech-recognition turn
# ---------------------------------------------------------------------------

@router.post("/webhooks/voice/respond", dependencies=[Depends(verify_twilio_signature)])
@limiter.limit("120/minute")
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

    # Persist the inbound message in its own transaction so an agent crash can't lose it.
    await save_message(db, conversation, MessageDirection.inbound, speech_result)
    await db.commit()

    # Hard daily cap per business — skip the LLM if exceeded.
    if await _over_daily_cap(db, business.id):
        await save_message(db, conversation, MessageDirection.outbound, LIMIT_REACHED_REPLY)
        await db.commit()
        publish(business.id, "conversation.updated", {"conversation_id": conversation.id})
        response.say(LIMIT_REACHED_REPLY, voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

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
