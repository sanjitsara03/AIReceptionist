from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather

from app.config import settings, pt_today_bounds
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
NOT_ALLOWED_REPLY = (
    "This is a private demo line. Please contact the business directly. "
    "Thanks!"
)
NOT_ALLOWED_VOICE = (
    "This is a private demonstration line. Please contact the business directly. Goodbye."
)


def _caller_allowed(from_number: str | None) -> bool:
    """Return True if this caller is allowed to interact with the AI.

    Empty SMS_ALLOWLIST = allow everyone (production / A2P-approved mode).
    Otherwise the from_number must match an entry exactly (E.164 form).
    """
    allow = settings.sms_allowlist_set
    if not allow:
        return True
    return bool(from_number) and from_number in allow


# ---------------------------------------------------------------------------
# Twilio request signature validation
# ---------------------------------------------------------------------------

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

    # When the operator has explicitly pinned WEBHOOK_BASE_URL, trust ONLY
    # that — otherwise a caller could forge an X-Forwarded-Host that we
    # happen to accept, weakening the signature check.
    if settings.webhook_base_url:
        base = settings.webhook_base_url.rstrip("/")
        return [f"{base}{path}{qs}"]

    fwd_host = (request.headers.get("X-Forwarded-Host") or request.url.netloc).split(",")[0].strip()
    fwd_proto = (request.headers.get("X-Forwarded-Proto") or request.url.scheme).split(",")[0].strip()

    candidates: list[str] = [
        f"https://{fwd_host}{path}{qs}",
        f"{fwd_proto}://{fwd_host}{path}{qs}",
        str(request.url),
    ]

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
    # "Today" = California-local day so the cap resets at PT midnight, not 5pm PT.
    since, _ = pt_today_bounds()

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


def sanitize_for_speech(text: str) -> str:
    """Strip markdown/table artifacts that TTS reads literally.

    Polly reads "|" as "vertical bar", "**" as "asterisk asterisk", etc.
    Even with strong prompt rules, models slip occasionally — sanitize
    defensively before handing text to <Say> or <Message>.
    """
    import re
    out = strip_emojis(text)
    # Drop pure separator rows like "|---|---|---|"
    out = re.sub(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$", "", out, flags=re.MULTILINE)
    # Drop pipe characters and surrounding spaces
    out = out.replace("|", " ")
    # Strip markdown emphasis markers
    out = re.sub(r"(\*\*|__|`)", "", out)
    # Strip lone "#" tokens (markdown headings or table column markers).
    # Doesn't touch "#123" style since there's no boundary after the digit.
    out = re.sub(r"(?<!\S)#+(?!\S)", "", out)
    # Strip leading bullets/numbers on lines
    out = re.sub(r"^[\s>#]*[-*•]\s+", "", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*\d+[.)]\s+", "", out, flags=re.MULTILINE)
    # Collapse whitespace
    out = re.sub(r"\s+", " ", out).strip()

    # Strip "Day Date Time" / "Date Time" / "Slot Day Date Time" headers
    # the model emits as a faked table header even when pipes are forbidden.
    # Matches anywhere — the header rarely starts the message; usually it
    # follows a lead-in like "Here are our times: ".
    out = re.sub(
        r"\b(?:Slot\s+ID\s+|Slot\s+)?(?:Day\s+)?Date\s+Time\b\s*[:,.-]?\s*",
        "",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\b(?:Slot\s+)?Day\s+Date\s+Time\b\s*[:,.-]?\s*",
        "",
        out,
        flags=re.IGNORECASE,
    )

    # Insert a period between back-to-back times so TTS pauses correctly.
    # Pattern: "...3:30 PM Thursday May 28 8:00 AM..." → "...3:30 PM. Thursday May 28 8:00 AM..."
    days = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
    out = re.sub(
        rf"(\d{{1,2}}:\d{{2}}\s*(?:AM|PM|am|pm))\s+(?=(?:{days})\b)",
        r"\1. ",
        out,
    )

    # Strip any leftover [internal:...] tags the model might echo despite the prompt.
    out = re.sub(r"\[internal:[^\]]*\]", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


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

    # Capture IDs as raw ints — agent.run() may rollback the session and expire ORM objects.
    business_id = business.id
    conversation_id = conversation.id

    # Persist the inbound message in its own transaction so an agent crash can't lose it.
    await save_message(db, conversation_id, MessageDirection.inbound, body)
    await db.commit()

    # Allowlist gate (demo mode). Drop random callers BEFORE invoking the LLM
    # so they can't create fake bookings or burn Claude tokens. We still save
    # the inbound message above so attempted abuse is visible in the dashboard.
    if not _caller_allowed(from_number):
        await save_message(db, conversation_id, MessageDirection.outbound, NOT_ALLOWED_REPLY)
        await db.commit()
        publish(business_id, "conversation.updated", {"conversation_id": conversation_id})
        response = MessagingResponse()
        response.message(NOT_ALLOWED_REPLY)
        return Response(content=str(response), media_type="application/xml")

    # Hard daily cap per business — skip the LLM if exceeded.
    if await _over_daily_cap(db, business_id):
        await save_message(db, conversation_id, MessageDirection.outbound, LIMIT_REACHED_REPLY)
        await db.commit()
        publish(business_id, "conversation.updated", {"conversation_id": conversation_id})
        response = MessagingResponse()
        response.message(LIMIT_REACHED_REPLY)
        return Response(content=str(response), media_type="application/xml")

    # Load full history and get AI reply
    history = await load_history(db, conversation)
    deps = AgentDeps(db=db, business_id=business_id, business=business, customer=customer)
    reply = sanitize_for_speech(await get_ai_reply(history, deps))

    # Save outbound — uses int IDs so it works even if the agent rolled back.
    await save_message(db, conversation_id, MessageDirection.outbound, reply)
    await db.commit()

    publish(business_id, "conversation.updated", {"conversation_id": conversation_id})

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
    from_number = form.get("From")

    # Allowlist gate (demo mode) — reject random callers immediately, no DB writes.
    if not _caller_allowed(from_number):
        response = VoiceResponse()
        response.say(NOT_ALLOWED_VOICE, voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

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

    # Allowlist gate — belt-and-suspenders in case the entry handler was bypassed.
    if not _caller_allowed(from_number):
        response.say(NOT_ALLOWED_VOICE, voice="Polly.Joanna")
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

    # Capture IDs as raw ints — agent.run() may rollback the session and expire ORM objects.
    business_id = business.id
    conversation_id = conversation.id

    # Persist the inbound message in its own transaction so an agent crash can't lose it.
    await save_message(db, conversation_id, MessageDirection.inbound, speech_result)
    await db.commit()

    # Hard daily cap per business — skip the LLM if exceeded.
    if await _over_daily_cap(db, business_id):
        await save_message(db, conversation_id, MessageDirection.outbound, LIMIT_REACHED_REPLY)
        await db.commit()
        publish(business_id, "conversation.updated", {"conversation_id": conversation_id})
        response.say(LIMIT_REACHED_REPLY, voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # Get AI reply. Sanitize once at the source so the DB, dashboard, and
    # TwiML all see the same clean, table-free, markdown-free text.
    history = await load_history(db, conversation)
    deps = AgentDeps(db=db, business_id=business_id, business=business, customer=customer)
    reply = sanitize_for_speech(await get_ai_reply(history, deps))

    # Save AI reply — uses int IDs so it works even if the agent rolled back.
    await save_message(db, conversation_id, MessageDirection.outbound, reply)
    await db.commit()

    publish(business_id, "conversation.updated", {"conversation_id": conversation_id})

    # Speak the reply and listen again
    gather = Gather(
        input="speech",
        action="/webhooks/voice/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.say(reply, voice="Polly.Joanna")
    response.append(gather)

    # If customer doesn't say anything, hang up politely
    response.say("We didn't hear anything. Goodbye!", voice="Polly.Joanna")

    return Response(content=str(response), media_type="application/xml")
