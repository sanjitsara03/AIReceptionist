from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Customer, Conversation, Message, MessageDirection


async def get_or_create_customer(db: AsyncSession, business_id: int, phone: str) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.business_id == business_id, Customer.phone == phone)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        customer = Customer(business_id=business_id, name="Unknown", phone=phone)
        db.add(customer)
        await db.flush()

    return customer


async def get_or_create_conversation(db: AsyncSession, customer: Customer) -> Conversation:
    # Use .limit(1) — a customer can have multiple historical conversations.
    # We grab the most recent one.
    result = await db.execute(
        select(Conversation)
        .where(Conversation.customer_id == customer.id)
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        conversation = Conversation(customer_id=customer.id)
        db.add(conversation)
        await db.flush()

    return conversation


# Max prior messages fed to the AI on each turn. ~15 turns of context is enough
# for the agent to stay coherent and keeps the per-reply Claude bill bounded for
# customers who text us hundreds of times over months.
MAX_HISTORY_MESSAGES = 30


async def load_history(db: AsyncSession, conversation: Conversation) -> list[dict]:
    # Grab the most recent MAX_HISTORY_MESSAGES, then reverse to chronological
    # order so the agent reads them oldest → newest.
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
    )
    messages = list(reversed(result.scalars().all()))

    history = []
    for message in messages:
        role = "user" if message.direction == MessageDirection.inbound else "assistant"
        history.append({"role": role, "content": message.body})

    return history


async def save_message(db: AsyncSession, conversation: Conversation, direction: MessageDirection, body: str) -> Message:
    message = Message(conversation_id=conversation.id, direction=direction, body=body)
    db.add(message)
    await db.flush()
    return message
