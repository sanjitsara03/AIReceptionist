import os
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, UserPromptPart, TextPart
from pydantic_ai.usage import UsageLimits

from app.config import settings
from app.agent.tools import AgentDeps, check_availability, book_job, reschedule_job, cancel_job, list_my_appointments

# Cap LLM round-trips and tokens per .run() so a runaway loop can't burn spend.
AGENT_USAGE_LIMITS = UsageLimits(request_limit=5, total_tokens_limit=10000)

os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

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
agent.tool(list_my_appointments)


@agent.system_prompt
async def build_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    b = ctx.deps.business
    # Owner-customized prompt from Settings takes precedence.
    if b.system_prompt and b.system_prompt.strip():
        return b.system_prompt
    return BASE_SYSTEM_PROMPT.format(
        business_name=b.name,
        services=b.services or "General home services",
        hours=b.hours or "Please call for hours",
        address=b.address or "Please call for location",
    )


def build_message_history(history: list[dict]) -> list[ModelMessage]:
    messages = []
    for msg in history[:-1]:
        if msg["role"] == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=msg["content"])]))
    return messages


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
        return result.output
    except Exception as e:
        # Fail closed with a generic reply so Twilio doesn't 500-and-retry; report to Sentry.
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(e)
        except Exception:
            pass
        return (
            "Sorry — I'm having trouble responding right now. "
            "Please try again in a moment or call back."
        )
