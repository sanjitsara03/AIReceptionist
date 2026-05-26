from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Customer, Conversation, Message, MessageDirection

# A conversation older than this is treated as stale — the next inbound
# starts a fresh thread. Keeps message rows bounded and gives the agent
# a clean history window.
CONVERSATION_STALE_AFTER = timedelta(days=7)


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


async def get_or_create_conversation(
    db: AsyncSession, customer: Customer, channel: str = "sms"
) -> Conversation:
    """
    Find the customer's most recent conversation, or create a new one tagged
    with `channel` ("sms" or "voice").

    If the most recent conversation is in a DIFFERENT channel than the current
    contact (e.g. last time they texted, now they're calling), we treat it as
    a new conversation — the channel is part of the conversation's identity.
    """
    result = await db.execute(
        select(Conversation)
        .where(Conversation.customer_id == customer.id)
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()

    stale = False
    if conversation is not None:
        last_active = conversation.updated_at or conversation.created_at
        if last_active is not None:
            # updated_at from the DB is timezone-aware (DateTime(timezone=True))
            if datetime.now(timezone.utc) - last_active > CONVERSATION_STALE_AFTER:
                stale = True

    if conversation is None or conversation.channel != channel or stale:
        conversation = Conversation(customer_id=customer.id, channel=channel)
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


async def save_message(db: AsyncSession, conversation_id: int, direction: MessageDirection, body: str) -> Message:
    # Takes a raw int (not the Conversation ORM object) so callers can keep
    # working even if the session was rolled back and the ORM object expired.
    message = Message(conversation_id=conversation_id, direction=direction, body=body)
    db.add(message)
    # Bump the conversation's updated_at so the staleness check in
    # get_or_create_conversation reflects last activity, not last edit.
    conv = await db.get(Conversation, conversation_id)
    if conv is not None:
        conv.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return message
