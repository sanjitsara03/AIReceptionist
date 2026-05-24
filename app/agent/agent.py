import os
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, UserPromptPart, TextPart

from app.config import settings
from app.agent.tools import AgentDeps, check_availability, book_job, reschedule_job, cancel_job

os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

SYSTEM_PROMPT = """You are an AI receptionist for a home service business. Your job is to help customers via SMS.

You can help customers:
- Book a new appointment
- Reschedule an existing appointment
- Cancel an appointment
- Answer basic questions about the business

When a customer wants to book, first check availability, then confirm the slot with the customer before booking.
Keep your replies short and conversational — this is SMS, not email. Never write long paragraphs.
Always be friendly and professional.
If you are not sure about something, ask the customer to clarify."""

agent = Agent(
    model="anthropic:claude-sonnet-4-6",
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
)

agent.tool(check_availability)
agent.tool(book_job)
agent.tool(reschedule_job)
agent.tool(cancel_job)


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

    result = await agent.run(current_message, message_history=history, deps=deps)
    return result.output
