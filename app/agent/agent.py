import logging
import os
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    UserPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.usage import UsageLimits

from app.config import settings
from app.agent.tools import (
    AgentDeps,
    check_availability,
    book_job,
    reschedule_job,
    cancel_job,
    cancel_all_jobs,
    list_my_appointments,
)

# Cap LLM round-trips and tokens per .run() so a runaway loop can't burn spend.
AGENT_USAGE_LIMITS = UsageLimits(request_limit=8, total_tokens_limit=15000)

os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

# Always appended after either BASE_SYSTEM_PROMPT or the owner's custom prompt — these are
# operational rules (multi-tenant safety, tool usage, voice/SMS hygiene) that owners shouldn't
# be able to override by editing their personality prompt in Settings.
OPERATIONAL_RULES = """OPERATIONAL RULES (always follow these regardless of personality):

1. NEVER ask the customer for a "job ID", "appointment ID", "confirmation number", or anything similar — they will not have one. You already know who they are from their phone number.
   - "What appointments do I have?" → call list_my_appointments. Do not ask first.
   - "I'd like to cancel/reschedule my appointment" → call list_my_appointments FIRST to see what they have. If they have exactly one, confirm the date/service and proceed. If multiple, ask which one (by date or service, never by ID).

2. ACTIONS ARE ONLY REAL IF YOU CALL THE TOOL. This applies to booking, cancelling, AND rescheduling:
   - Never tell a customer an appointment is "booked", "confirmed", or "scheduled" unless you called book_job for THAT slot in THIS turn and received a success message.
   - Never tell a customer an appointment is "cancelled" unless you called cancel_job for THAT job in THIS turn and received a success message.
   - Never tell a customer an appointment is "rescheduled" unless you called reschedule_job for THAT job in THIS turn and received a success message.
   Past confirmations in the conversation history do NOT count — only tool replies you received during this turn. If the customer requests multiple operations, call the tool once per operation. If you forget which ones you've actually done, call list_my_appointments to verify before responding. Confirming an action that didn't actually happen is the single worst mistake you can make.

3. For booking: call check_availability, confirm the slot with the customer in plain language (date + time), then call book_job.

4. For cancelling or rescheduling a SPECIFIC appointment: ALWAYS call list_my_appointments first. Match the customer's words ("my drain cleaning", "Tuesday at 2") to one of the returned Job entries, then call cancel_job or reschedule_job with that job's id. If multiple match, ask the customer which one (by date/service, never by id). If none match, tell the customer you don't see that appointment.

5. For cancelling ALL appointments at once ("cancel everything", "cancel all my appointments", "wipe my schedule", "I won't make any of them"): call cancel_all_jobs — a single tool call that cancels every upcoming job for this caller. Do NOT loop cancel_job per appointment. Do NOT ask "which one" — the customer told you all.

6. Replies are spoken aloud via TTS or sent as SMS. Output PLAIN PROSE ONLY:
   - No emojis.
   - No markdown of any kind: no asterisks, no underscores, no bullet symbols, no checkmarks, no headings, no code fences.
   - NO TABLES. No pipe characters (|). No grid layouts. TTS reads "|" out loud as "vertical bar" — never include one.
   - No numbered or bulleted lists. When listing options, use natural prose with commas or "or", e.g. "I have Wednesday May 27 at 3:30 PM, or Thursday May 28 at 8:00 AM. Which works?"
   - No long paragraphs. Short, conversational sentences only.

7. If a tool returns an error message, do not retry it more than once. Apologize and offer to have someone call the customer back."""

BASE_SYSTEM_PROMPT = """You are an AI receptionist for {business_name}. Your job is to help customers via SMS and voice calls.

Business information:
- Name: {business_name}
- Services: {services}
- Hours: {hours}
- Address: {address}

You can help customers:
- Answer questions about the business, services, hours, and location
- Book a new appointment
- Look up the customer's existing appointments
- Reschedule an existing appointment
- Cancel an appointment

IMPORTANT — appointment lookup:
You already know the caller's phone number, and you can look up their
appointments yourself using the list_my_appointments tool. NEVER ask the
customer for a "job ID", "appointment ID", "confirmation number", or
similar — they will not have one. Instead:
  - If they ask "what appointments do I have?" → call list_my_appointments.
  - If they want to reschedule or cancel and don't specify which appointment
    → call list_my_appointments first, then ask them which one they mean
    (by date/time or service), then use the job id from the tool result to
    call reschedule_job or cancel_job.

When a customer wants to book, first check availability with check_availability,
then confirm the slot with the customer before calling book_job.

Keep your replies short and conversational. Never write long paragraphs.
Do not use emojis. Do not use markdown formatting like ** or *.
Always be friendly and professional.
If you are not sure about something, ask the customer to clarify."""

agent = Agent(
    model="anthropic:claude-sonnet-4-6",
    deps_type=AgentDeps,
)

agent.tool(check_availability)
agent.tool(book_job)
agent.tool(reschedule_job)
agent.tool(cancel_job)
agent.tool(cancel_all_jobs)
agent.tool(list_my_appointments)


@agent.system_prompt
async def build_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    b = ctx.deps.business
    # Owner can customize personality; operational rules always append underneath.
    if b.system_prompt and b.system_prompt.strip():
        base = b.system_prompt.strip()
    else:
        base = BASE_SYSTEM_PROMPT.format(
            business_name=b.name,
            services=b.services or "General home services",
            hours=b.hours or "Please call for hours",
            address=b.address or "Please call for location",
        )
    return base + "\n\n" + OPERATIONAL_RULES


def build_message_history(history: list[dict]) -> list[ModelMessage]:
    messages = []
    for msg in history[:-1]:
        if msg["role"] == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=msg["content"])]))
    return messages


log = logging.getLogger("agent.tools")


def _log_tool_calls(result, business_id: int) -> None:
    """Emit a log line + Sentry breadcrumb for every tool call this turn.

    Lets us verify after the fact whether the agent actually called book_job
    (vs. hallucinating a confirmation in plain text). new_messages() is the
    delta produced by this run, so we don't re-log historical tool calls.
    """
    try:
        new_msgs = result.new_messages()
    except Exception:
        return

    try:
        import sentry_sdk
    except Exception:
        sentry_sdk = None

    by_id: dict[str, str] = {}
    for msg in new_msgs:
        for part in getattr(msg, "parts", []) or []:
            if isinstance(part, ToolCallPart):
                call_id = getattr(part, "tool_call_id", None)
                name = getattr(part, "tool_name", "unknown")
                args = getattr(part, "args", None)
                if call_id:
                    by_id[call_id] = name
                log.info("tool_call business=%s name=%s args=%s", business_id, name, args)
                if sentry_sdk:
                    sentry_sdk.add_breadcrumb(
                        category="agent.tool_call",
                        message=name,
                        data={"business_id": business_id, "args": str(args)[:500]},
                        level="info",
                    )
            elif isinstance(part, ToolReturnPart):
                call_id = getattr(part, "tool_call_id", None)
                name = by_id.get(call_id, "unknown") if call_id else "unknown"
                content = getattr(part, "content", None)
                log.info("tool_return business=%s name=%s result=%s", business_id, name, str(content)[:500])
                if sentry_sdk:
                    sentry_sdk.add_breadcrumb(
                        category="agent.tool_return",
                        message=name,
                        data={"business_id": business_id, "result": str(content)[:500]},
                        level="info",
                    )


async def get_ai_reply(conversation_history: list[dict], deps: AgentDeps) -> str:
    if not conversation_history:
        return "Hi! How can I help you today?"

    current_message = conversation_history[-1]["content"]
    history = build_message_history(conversation_history)

    try:
        result = await agent.run(
            current_message,
            message_history=history,
            deps=deps,
            usage_limits=AGENT_USAGE_LIMITS,
        )
        _log_tool_calls(result, deps.business_id)
        return result.output
    except Exception as e:
        # Roll back the poisoned session — a tool's failed flush leaves it in
        # PendingRollbackError state, which would crash the caller's save_message.
        try:
            await deps.db.rollback()
        except Exception:
            pass
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(e)
        except Exception:
            pass
        return (
            "Sorry — I'm having trouble responding right now. "
            "Please try again in a moment or call back."
        )
