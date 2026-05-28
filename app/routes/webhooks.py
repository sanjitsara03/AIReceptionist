import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Response, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather

from app.config import settings, pt_today_bounds
from app.database import AsyncSessionLocal, get_db
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

log = logging.getLogger("webhooks.voice")

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
    """True if this caller can interact with the AI; empty allowlist means allow all."""
    allow = settings.sms_allowlist_set
    if not allow:
        return True
    return bool(from_number) and from_number in allow


# Twilio request signature validation

def _candidate_urls(request: Request) -> list[str]:
    """Build URLs to try matching the Twilio signature against; first match wins."""
    path = request.url.path
    qs = f"?{request.url.query}" if request.url.query else ""

    # When WEBHOOK_BASE_URL is pinned, trust ONLY that to avoid X_Forwarded_Host forgery.
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

    # Dedupe while preserving order
    seen, unique = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


async def verify_twilio_signature(request: Request) -> None:
    if not settings.validate_twilio_signature:
        return  # disabled in tests

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Twilio signature.")

    form = await request.form()
    form_dict = {k: v for k, v in form.items()}

    validator = RequestValidator(settings.twilio_auth_token)
    for url in _candidate_urls(request):
        if validator.validate(url, form_dict, signature):
            return

    # Log mismatch context without leaking the auth token.
    import logging
    logging.getLogger("twilio.signature").warning(
        "Twilio signature mismatch. tried=%s host=%s fwd_host=%s fwd_proto=%s",
        _candidate_urls(request),
        request.url.netloc,
        request.headers.get("X-Forwarded-Host"),
        request.headers.get("X-Forwarded-Proto"),
    )
    raise HTTPException(status_code=403, detail="Invalid Twilio signature.")


# Per business daily message cap

async def _over_daily_cap(db: AsyncSession, business_id: int) -> bool:
    cap = settings.daily_message_limit_per_business
    if cap <= 0:
        return False
    # "Today" is California local so the cap resets at PT midnight, not 5pm PT.
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
    """Strip markdown/table artifacts so TTS does not read them literally."""
    import re
    out = strip_emojis(text)
    # Drop pure markdown separator rows like the "|---|---|" row of a table.
    out = re.sub(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$", "", out, flags=re.MULTILINE)
    # Drop pipe characters and surrounding spaces
    out = out.replace("|", " ")
    # Strip markdown emphasis markers
    out = re.sub(r"(\*\*|__|`)", "", out)
    # Strip lone "#" tokens (markdown headings); "#123" style is preserved.
    out = re.sub(r"(?<!\S)#+(?!\S)", "", out)
    # Strip leading bullets/numbers on lines
    out = re.sub(r"^[\s>#]*[-*•]\s+", "", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*\d+[.)]\s+", "", out, flags=re.MULTILINE)
    # Collapse whitespace
    out = re.sub(r"\s+", " ", out).strip()

    # Strip fake table headers the model emits even when pipes are forbidden.
    out = re.sub(
        r"\b(?:Slot\s+ID\s+|Slot\s+)?(?:Day\s+)?Date\s+Time\b\s*[:,.]?\s*",
        "",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\b(?:Slot\s+)?Day\s+Date\s+Time\b\s*[:,.]?\s*",
        "",
        out,
        flags=re.IGNORECASE,
    )

    # Insert a period between back to back times so TTS pauses correctly.
    days = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
    out = re.sub(
        rf"(\d{{1,2}}:\d{{2}}\s*(?:AM|PM|am|pm))\s+(?=(?:{days})\b)",
        r"\1. ",
        out,
    )

    # Strip any leftover [internal:...] tags the model may echo despite the prompt.
    out = re.sub(r"\[internal:[^\]]*\]", "", out)

    # Run on list breakup. When the model emits 3+ comma separated short noun
    # phrases (e.g. service or appointment lists), swap inner commas for
    # periods so TTS pauses between items. Two equivalent shapes match:
    #   "X, Y, Z"           (>= 2 comma items)
    #   "X, Y, and/or Z"    (1 comma item + trailing connector)
    # Items are up to 3 words and may not start with "and"/"or" (those are connectors).
    item = r"(?!and\b|or\b)[A-Za-z][A-Za-z]+(?:\s+[A-Za-z]+){0,2}"
    connector = rf"\s*,?\s*(?:and|or)\s+{item}"
    list_re = re.compile(
        rf"\b({item})(?:(?:,\s*{item}){{2,}}(?:{connector})?|(?:,\s*{item}){{1,}}{connector})",
        re.IGNORECASE,
    )
    def _break_list(m: re.Match) -> str:
        text = m.group(0)
        # Replace " and X" / " or X" / ", and X" / ", or X" connectors with ", "
        # so all items are now comma separated.
        text = re.sub(r"\s*,?\s*(?:and|or)\s+", ", ", text, flags=re.IGNORECASE)
        parts = [p.strip() for p in text.split(",") if p.strip()]
        # Capitalize each part EXCEPT the first so the surrounding sentence start is preserved.
        out_parts = [parts[0]] + [p[0].upper() + p[1:] if p else p for p in parts[1:]]
        # No trailing period; the surrounding text already has its own punctuation.
        return ". ".join(out_parts)
    out = list_re.sub(_break_list, out)

    out = re.sub(r"\s+", " ", out).strip()
    return out


# Background agent execution for the voice ack/process pipeline.
# Maps conversation_id to the asyncio.Task running the agent for the current
# turn. In process, in memory, single worker only (same constraint as the
# SSE broker in app/events.py).
_pending_replies: dict[int, asyncio.Task] = {}


import random


# Acknowledgement phrases, grouped by intent. Each call picks one at random so
# repeat turns within a call don't all sound the same. Checks are ordered
# specific to general so reschedule doesn't get caught by the broader
# 'schedule' availability matcher.
_ACKS = {
    "reschedule": [
        "Let me see what's available.",
        "Sure, let me find another slot.",
        "Got it, checking what we can move you to.",
    ],
    "cancel": [
        "Let me look that up.",
        "Sure, let me pull up your appointment.",
        "Okay, one second.",
    ],
    "list": [
        "Let me pull that up for you.",
        "Sure, looking up your appointments now.",
        "One second, checking your file.",
    ],
    "availability": [
        "Let me check our availability.",
        "One second, checking the schedule.",
        "Sure, let me see what we have open.",
    ],
    "closing": [
        "Got it.",
        "Alright.",
        "Sounds good.",
        "Okay.",
    ],
    "greeting": [
        "Sure, how can I help?",
        "Hi there!",
        "Of course.",
    ],
    "default": [
        "One moment please.",
        "One second.",
        "Sure, give me a moment.",
        "Alright, hang on.",
    ],
}


def _acknowledgement_for(speech: str) -> str:
    """Pick a short intent matching acknowledgement to play while the agent runs."""
    s = (speech or "").lower().strip()

    # Conversation-ending intents: short replies like "no", "no thanks",
    # "that's it", "goodbye", "I'm good". The agent's actual response will
    # likely be a farewell, so the ack should feel like a casual acknowledgment.
    if s in {"no", "nope", "no thanks", "no thank you"} or any(
        p in s for p in ("that's it", "thats it", "that's all", "thats all",
                          "goodbye", "good bye", "bye", "i'm good", "im good",
                          "i'm done", "im done", "nothing else", "all set")):
        return random.choice(_ACKS["closing"])

    # Greeting only (no other content)
    if s in {"hi", "hello", "hey", "yo"}:
        return random.choice(_ACKS["greeting"])

    if any(w in s for w in ("reschedul", "move my", "change my")):
        return random.choice(_ACKS["reschedule"])
    if "cancel" in s:
        return random.choice(_ACKS["cancel"])
    if any(w in s for w in ("what do i have", "my appointment", "my booking", "what's booked", "whats booked")):
        return random.choice(_ACKS["list"])
    if any(w in s for w in ("available", "when", " time", "book", "schedule", "appointment slot")):
        return random.choice(_ACKS["availability"])
    return random.choice(_ACKS["default"])


async def _run_agent_isolated(conversation_id: int, business_id: int, customer_id: int) -> str:
    """Run the agent in a fresh DB session.

    The original request's session closes when /respond returns, so the
    background task needs its own session for tool calls and the outbound
    save. Returns the sanitized reply text so /process can speak it.
    """
    async with AsyncSessionLocal() as db:
        business = await db.get(Business, business_id)
        customer = await db.get(Customer, customer_id)
        conv = await db.get(Conversation, conversation_id)
        if not business or not customer or not conv:
            raise RuntimeError("business, customer, or conversation missing mid-call")

        history = await load_history(db, conv)
        deps = AgentDeps(db=db, business_id=business_id, business=business, customer=customer)
        reply = sanitize_for_speech(await get_ai_reply(history, deps))

        await save_message(db, conversation_id, MessageDirection.outbound, reply)
        await db.commit()
        publish(business_id, "conversation.updated", {"conversation_id": conversation_id})
        return reply


# SMS webhook

@router.post("/webhooks/sms", dependencies=[Depends(verify_twilio_signature)])
@limiter.limit("60/minute")
async def inbound_sms(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()

    from_number = form.get("From")
    to_number = form.get("To")
    body = form.get("Body")

    # Twilio occasionally posts malformed test payloads; bail early.
    if not from_number or not to_number or not body:
        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # Look up business by Twilio number
    result = await db.execute(select(Business).where(Business.twilio_number == to_number))
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail="Business not found for this number")

    # Get or create customer and conversation (SMS only)
    customer = await get_or_create_customer(db, business.id, from_number)
    conversation = await get_or_create_conversation(db, customer, channel="sms")

    # Raw int IDs survive ORM expiration if agent.run rolls back the session.
    business_id = business.id
    conversation_id = conversation.id

    # Persist inbound in its own transaction so an agent crash cannot lose it.
    await save_message(db, conversation_id, MessageDirection.inbound, body)
    await db.commit()

    # Demo mode allowlist: drop random callers BEFORE invoking the LLM. Inbound is still saved for audit.
    if not _caller_allowed(from_number):
        await save_message(db, conversation_id, MessageDirection.outbound, NOT_ALLOWED_REPLY)
        await db.commit()
        publish(business_id, "conversation.updated", {"conversation_id": conversation_id})
        response = MessagingResponse()
        response.message(NOT_ALLOWED_REPLY)
        return Response(content=str(response), media_type="application/xml")

    # Hard daily cap per business; skip the LLM if exceeded.
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

    # Save outbound; raw int IDs work even if the agent rolled back.
    await save_message(db, conversation_id, MessageDirection.outbound, reply)
    await db.commit()

    publish(business_id, "conversation.updated", {"conversation_id": conversation_id})

    response = MessagingResponse()
    response.message(reply)

    return Response(content=str(response), media_type="application/xml")


# Voice webhook initial greeting

@router.post("/webhooks/voice", dependencies=[Depends(verify_twilio_signature)])
@limiter.limit("60/minute")
async def inbound_call(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    to_number = form.get("To")
    from_number = form.get("From")

    # Demo mode allowlist: reject random callers immediately with no DB writes.
    if not _caller_allowed(from_number):
        response = VoiceResponse()
        response.say(NOT_ALLOWED_VOICE, voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # Greeting
    greeting = VOICE_GREETING
    if to_number:
        result = await db.execute(select(Business).where(Business.twilio_number == to_number))
        business = result.scalar_one_or_none()
        if business:
            if business.voice_greeting and business.voice_greeting.strip():
                greeting = business.voice_greeting
            else:
                greeting = (
                    f"Hi! You've reached the AI receptionist for {business.name}. "
                    "How can I help you today?"
                )

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


# Voice webhook per speech recognition turn

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

    # Allowlist gate: belt and suspenders in case the entry handler was bypassed.
    if not _caller_allowed(from_number):
        response.say(NOT_ALLOWED_VOICE, voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # If the caller said nothing, prompt again rather than hitting the agent with empty input.
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

    # Get or create customer and conversation (voice only)
    customer = await get_or_create_customer(db, business.id, from_number)
    conversation = await get_or_create_conversation(db, customer, channel="voice")

    # Raw int IDs survive ORM expiration if agent.run rolls back the session.
    business_id = business.id
    conversation_id = conversation.id

    # Persist inbound in its own transaction so an agent crash cannot lose it.
    await save_message(db, conversation_id, MessageDirection.inbound, speech_result)
    await db.commit()

    # Hard daily cap per business; skip the LLM if exceeded.
    if await _over_daily_cap(db, business_id):
        await save_message(db, conversation_id, MessageDirection.outbound, LIMIT_REACHED_REPLY)
        await db.commit()
        publish(business_id, "conversation.updated", {"conversation_id": conversation_id})
        response.say(LIMIT_REACHED_REPLY, voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # Kick off agent.run in the background. The customer hears the
    # acknowledgement TTS during the ~1.5s while the agent does its work, so
    # perceived latency drops. /webhooks/voice/process picks up the result.
    prior = _pending_replies.pop(conversation_id, None)
    if prior and not prior.done():
        prior.cancel()  # customer started a new turn before we delivered the old one

    customer_id = customer.id
    task = asyncio.create_task(
        _run_agent_isolated(conversation_id, business_id, customer_id)
    )
    _pending_replies[conversation_id] = task

    response.say(_acknowledgement_for(speech_result), voice="Polly.Joanna")
    response.redirect(
        f"/webhooks/voice/process?conversation_id={conversation_id}",
        method="POST",
    )
    return Response(content=str(response), media_type="application/xml")


@router.post("/webhooks/voice/process", dependencies=[Depends(verify_twilio_signature)])
@limiter.limit("120/minute")
async def voice_process(request: Request, conversation_id: int):
    """Pickup endpoint: await the background agent task and speak its reply."""
    response = VoiceResponse()
    task = _pending_replies.pop(conversation_id, None)

    if task is None:
        # Worker restart, duplicate Twilio delivery, or a missed handoff.
        # Drop the customer back into a fresh Gather rather than crashing the call.
        log.warning("voice_process: no pending task for conversation_id=%s", conversation_id)
        response.say(
            "Sorry, I lost track for a second. Could you say that again?",
            voice="Polly.Joanna",
        )
        gather = Gather(
            input="speech",
            action="/webhooks/voice/respond",
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        response.append(gather)
        return Response(content=str(response), media_type="application/xml")

    try:
        # Twilio's hard webhook timeout is 15s. Cap the agent at 12s so we
        # have room to render TwiML and respond gracefully on overrun.
        reply = await asyncio.wait_for(task, timeout=12)
    except asyncio.TimeoutError:
        log.warning("voice_process: agent timeout for conversation_id=%s", conversation_id)
        reply = "Sorry, I'm taking longer than expected. Please try again in a moment."
    except Exception:
        log.exception("voice_process: agent raised for conversation_id=%s", conversation_id)
        reply = "Sorry, something went wrong. Please try again."

    gather = Gather(
        input="speech",
        action="/webhooks/voice/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.say(reply, voice="Polly.Joanna")
    response.append(gather)
    response.say("We didn't hear anything. Goodbye!", voice="Polly.Joanna")
    return Response(content=str(response), media_type="application/xml")
