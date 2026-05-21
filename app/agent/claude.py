import anthropic
from app.config import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """You are an AI receptionist for a home service business. Your job is to help customers via SMS.

You can help customers:
- Book a new appointment
- Reschedule an existing appointment
- Cancel an appointment
- Answer basic questions about the business

Keep your replies short and conversational — this is SMS, not email. Never write long paragraphs.
Always be friendly and professional.
If you are not sure about something, ask the customer to clarify."""


async def get_ai_reply(conversation_history: list[dict]) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=conversation_history,
    )
    return response.content[0].text
