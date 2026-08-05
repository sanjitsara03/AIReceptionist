import logging
import os
from pydantic_ai import Agent, ModelSettings, RunContext
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
    set_customer_name,
    set_customer_address,
)

# Cap LLM round trips and tokens per .run() so a runaway loop can't burn spend.
# The ~2.2k-token system prompt is re-counted on every request (no cache
# discount on input_tokens like Anthropic had), so the token cap must cover
# request_limit full prompts.
AGENT_USAGE_LIMITS = UsageLimits(request_limit=8, total_tokens_limit=60000)

os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key

# Always appended after either BASE_SYSTEM_PROMPT or the owner's custom prompt ; these are operational rules (multi tenant safety, tool usage, voice/SMS hygiene) that owners shouldn't be able to override by editing their personality prompt in Settings.
OPERATIONAL_RULES = """OPERATIONAL RULES (always follow these regardless of personality):

1. NEVER ask the customer for a "job ID", "appointment ID", "confirmation number", or anything similar — they will not have one. You already know who they are from their phone number.
   - "What appointments do I have?" → call list_my_appointments. Do not ask first.
   - "I'd like to cancel/reschedule my appointment" → call list_my_appointments FIRST to see what they have. If they have exactly one, confirm the date/service and proceed. If multiple, ask which one (by date or service, never by ID).
   - Tool results contain internal identifiers wrapped in `[internal:slot_id=N]` or `[internal:job_id=N]` tags. These are for YOUR use only when calling other tools (book_job, cancel_job, reschedule_job). NEVER mention the tag, the field name, the number, or the word "slot id" / "job id" to the customer. Speak only in human terms: service name, day, and time.

2. ACTIONS ARE ONLY REAL IF YOU CALL THE TOOL. This applies to booking, cancelling, AND rescheduling:
   - Never tell a customer a NEW appointment is "booked", "confirmed", or "scheduled" unless you called book_job for THAT slot and received a success message, or the tool told you the customer is already booked for that time.
   - Never tell a customer an appointment is "cancelled" unless you called cancel_job for THAT job in THIS turn and received a success message.
   - Never tell a customer an appointment is "rescheduled" unless you called reschedule_job for THAT job in THIS turn and received a success message.
   RESTATING A PAST BOOKING IS NOT A NEW ACTION. book_job CREATES a brand-new appointment every time it succeeds — call it at most ONCE per appointment the customer asks for. If the conversation history already shows a booking was confirmed and the customer is NOT asking to book something additional (they are giving their name, saying thanks, saying goodbye, or asking what they have), do NOT call book_job again. To double-check what is on file, call list_my_appointments — it is read-only and always safe. If the customer requests multiple operations, call the tool once per operation. Confirming an action that never happened is the single worst mistake you can make; booking the same appointment twice is the second worst.

3. For booking: call check_availability, confirm the slot with the customer in plain language (date + time), then call book_job.

4. For cancelling or rescheduling a SPECIFIC appointment: ALWAYS call list_my_appointments first. Match the customer's words ("my drain cleaning", "Tuesday at 2") to one of the returned Job entries, then call cancel_job or reschedule_job with that job's id. If multiple match, ask the customer which one (by date/service, never by id). If none match, tell the customer you don't see that appointment.

5. For cancelling ALL appointments at once ("cancel everything", "cancel all my appointments", "wipe my schedule", "I won't make any of them"): call cancel_all_jobs — a single tool call that cancels every upcoming job for this caller. Do NOT loop cancel_job per appointment. Do NOT ask "which one" — the customer told you all.

6. Replies are spoken aloud via TTS or sent as SMS. Output PLAIN PROSE ONLY:
   - No emojis.
   - No markdown of any kind: no asterisks, no underscores, no bullet symbols, no checkmarks, no headings, no code fences.
   - NO TABLES. No pipe characters (|). No grid layouts. TTS reads "|" out loud as "vertical bar" — never include one.
   - No numbered or bulleted lists.
   - No long paragraphs. Short, conversational sentences only.

   LIST FORMATTING (important for TTS clarity):
   When you need to list multiple appointments, time options, OR services, use ONE sentence per item, ended with a PERIOD. Do NOT chain everything together with "and" or commas. The period gives TTS a natural pause so the customer can follow along.

   GOOD (each item is its own sentence, period at the end):
     "You have two appointments. First, a sink installation on Wednesday May 27 at 3:30 PM. Second, a drain cleaning on Thursday May 28 at 8:00 AM. Which would you like to talk about?"

   GOOD (when offering 2 choices):
     "I have Wednesday May 27 at 3:30 PM, or Thursday May 28 at 8:00 AM. Which works for you?"

   GOOD (when listing services):
     "We offer drain cleaning. Pipe repair. Water heater install. Leak detection. Bathroom plumbing. Which one do you need?"

   BAD (run-on services, hard to follow on a phone call):
     "We offer drain cleaning, pipe repair, water heater install, leak detection, and bathroom plumbing."

   BAD (run-on appointments):
     "You have a sink installation on Wednesday May 27 at 3:30 PM and a drain cleaning on Thursday May 28 at 8:00 AM."

   For 3+ items, always render each item as its own short sentence with a period at the end. NEVER use commas to separate items in a list of 3 or more.

7. If a tool returns an error message, do not retry it more than once. Apologize and offer to have someone call the customer back.

8. FIRST REPLY ON A BRAND NEW CONVERSATION. If the conversation history is empty (this is the customer's very first message) AND that message is generic/short (e.g. "hi", "hello", "hey", "yo", or a wave emoji), respond with a brief one sentence greeting, then ask "How can we help you today?", then offer "Would you like to hear about our services?" Keep it to two or three short sentences total. If the customer's first message is a SPECIFIC request (e.g. "I need a sink fixed", "what times are available?", "cancel my appointment"), skip the services offer and handle the request directly.

9. NEVER RE GREET. After the initial greeting (the first message in the conversation history, whether from you or from a TTS pre roll), do NOT start subsequent replies with "Hi", "Hello", "Hey", or any greeting word. The customer has already been greeted. Just answer their question. Acceptable openers for follow up turns: "Sure!", "Of course.", "We offer...", "Let me check.", or simply diving into the answer.

10. PRICE DISCLOSURE. Before you confirm a booking, mention the approximate price in plain language. Use the estimate returned by book_job's response. Always say "about $X" or "around $X" (never an exact figure) because pricing varies with parts and severity. Example: "That'll run about $180 plus parts if needed. Should I lock it in?". If no estimate is available, skip this sentence rather than guessing.

11. RETURNING CUSTOMER. The system prompt's CUSTOMER ON THIS CALL block tells you the caller's name (if known) and whether they have an address on file. If the name is known (not "Unknown"), address the customer by their first name in your first reply of the turn. Do this naturally; do not announce "Welcome back" on every single message, only on the first turn of a fresh call/conversation.

12. CAPTURE NAME AND ADDRESS FROM SMS. If the channel is "sms" and the customer sends a message that looks like a name + address (e.g. "Sarah Lee, 123 Main St San Francisco" or "this is John, 456 Oak Ave"), call set_customer_name and set_customer_address with the extracted values, then reply with a brief acknowledgement (e.g. "Thanks Sarah, you're all set!"). Skip name capture if "Name on file" is already a real name; skip address capture if "Address on file" is already populated. Do NOT call the tools with empty strings.

13. CAPTURE NAME ON VOICE WHEN OFFERED. If a voice caller introduces themselves ("This is Sarah", "I'm John"), call set_customer_name with their name. Do not ask them to repeat or spell it unless the speech transcript is obviously garbled. NEVER ask a voice caller for their address. Address capture happens via the post booking SMS, not on the call."""

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
    model=f"openrouter:{settings.agent_model}",
    deps_type=AgentDeps,
    # Replies are a few spoken/texted sentences; cap output so a single
    # degenerate completion can't run to the model's output ceiling. (The
    # Anthropic SDK always sent max_tokens=4096 — OpenRouter sends no cap
    # unless we set one, and UsageLimits only checks between requests.)
    model_settings=ModelSettings(max_tokens=1024),
)

agent.tool(check_availability)
agent.tool(book_job)
agent.tool(reschedule_job)
agent.tool(cancel_job)
agent.tool(cancel_all_jobs)
agent.tool(list_my_appointments)
agent.tool(set_customer_name)
agent.tool(set_customer_address)


@agent.system_prompt
async def build_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    b = ctx.deps.business
    c = ctx.deps.customer
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

    # Customer context block lets the agent personalize (greet by name when
    # known, skip the address ask when already on file, etc).
    name_on_file = (c.name or "").strip()
    name_known = bool(name_on_file) and name_on_file.lower() != "unknown"
    address_on_file = (c.address or "").strip()
    customer_block = (
        "\nCUSTOMER ON THIS CALL:\n"
        f"- Phone: {c.phone}\n"
        f"- Name on file: {name_on_file if name_known else 'Unknown (please capture if mentioned)'}\n"
        f"- Address on file: {address_on_file if address_on_file else 'None (capture when booking)'}\n"
        f"- Channel: {ctx.deps.channel}\n"
    )

    return base + customer_block + "\n\n" + OPERATIONAL_RULES


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


def _final_response_lacks_text(result) -> bool:
    """True when the run's last model response carried no actual reply text.

    Gemini via OpenRouter occasionally ends a tool chain with an empty
    completion. pydantic-ai then salvages text from an earlier message in the
    run (e.g. the pre-tool "One moment.") and returns it as result.output —
    which reads like a finished reply but never delivered the tool results.
    """
    try:
        msgs = result.new_messages()
    except Exception:
        return False
    for msg in reversed(msgs):
        if isinstance(msg, ModelResponse):
            return not any(
                isinstance(p, TextPart) and (p.content or "").strip()
                for p in msg.parts
            )
    return False


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
        if _final_response_lacks_text(result):
            # Nudge the model to actually answer. Continuing from
            # all_messages() keeps the executed tool calls in history, so
            # nothing (booking, cancellation) runs twice. The nudge text is
            # model-side only — it is never persisted to the conversation.
            result = await agent.run(
                "Your last reply was empty. Send the customer your final "
                "answer now, in plain prose, based on the tool results above.",
                message_history=result.all_messages(),
                deps=deps,
                usage_limits=AGENT_USAGE_LIMITS,
            )
            _log_tool_calls(result, deps.business_id)
        return result.output
    except Exception as e:
        # Roll back the poisoned session ; a tool's failed flush leaves it in PendingRollbackError state, which would crash the caller's save_message.
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
