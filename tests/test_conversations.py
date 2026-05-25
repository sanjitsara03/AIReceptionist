from sqlalchemy import select

from app.models import Customer, Conversation, Message, MessageDirection


async def test_list_conversations_empty(client, business):
    r = await client.get("/conversations")
    assert r.status_code == 200
    assert r.json() == []


async def test_messages_returned_in_order(client, business, db):
    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id).limit(1)
    )).scalar_one()
    conv = Conversation(customer_id=cust.id, channel="sms")
    db.add(conv)
    await db.flush()

    db.add_all([
        Message(conversation_id=conv.id, direction=MessageDirection.inbound, body="hi"),
        Message(conversation_id=conv.id, direction=MessageDirection.outbound, body="hello"),
        Message(conversation_id=conv.id, direction=MessageDirection.inbound, body="thanks"),
    ])
    await db.commit()

    r = await client.get("/conversations")
    convs = r.json()
    assert len(convs) == 1
    bodies = [m["body"] for m in convs[0]["messages"]]
    assert bodies == ["hi", "hello", "thanks"]
