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
    result = await db.execute(
        select(Conversation)
        .where(Conversation.customer_id == customer.id)
        .order_by(Conversation.created_at.desc())
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        conversation = Conversation(customer_id=customer.id)
        db.add(conversation)
        await db.flush()

    return conversation


async def load_history(db: AsyncSession, conversation: Conversation) -> list[dict]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()

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
