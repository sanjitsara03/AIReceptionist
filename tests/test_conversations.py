import pytest
from sqlalchemy import select

from app.models import Business, Customer, Conversation, Message, MessageDirection


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


# POST /conversations/{id}/messages ; owner SMS reply

class _FakeTwilio:
    """Records what would have been sent so the test can assert against it."""
    def __init__(self):
        self.sent = []
        self.messages = self
    def create(self, body, from_, to):
        self.sent.append({"body": body, "from": from_, "to": to})
        return {"sid": "SMfake"}


@pytest.fixture
def fake_twilio(monkeypatch):
    """Patch the module-level Twilio client so tests don't hit the real API."""
    from app.routes import conversations as conv_route
    fake = _FakeTwilio()
    monkeypatch.setattr(conv_route, "twilio_client", fake)
    return fake


async def test_owner_reply_sends_sms_and_persists(client, business, db, fake_twilio):
    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id).limit(1)
    )).scalar_one()
    conv = Conversation(customer_id=cust.id, channel="sms")
    db.add(conv)
    await db.commit()

    r = await client.post(
        f"/conversations/{conv.id}/messages",
        json={"body": "Thanks — see you Tuesday!"},
    )
    assert r.status_code == 201
    payload = r.json()
    assert payload["body"] == "Thanks — see you Tuesday!"
    assert payload["direction"] == "outbound"

    # Real Twilio call was attempted with the right from/to.
    assert len(fake_twilio.sent) == 1
    sent = fake_twilio.sent[0]
    assert sent["from"] == business.twilio_number
    assert sent["to"] == cust.phone

    # Row was persisted.
    rows = (await db.execute(
        select(Message).where(Message.conversation_id == conv.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].direction == MessageDirection.outbound


async def test_owner_reply_rejects_voice_conversation(client, business, db, fake_twilio):
    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id).limit(1)
    )).scalar_one()
    conv = Conversation(customer_id=cust.id, channel="voice")
    db.add(conv)
    await db.commit()

    r = await client.post(f"/conversations/{conv.id}/messages", json={"body": "hi"})
    assert r.status_code == 400
    assert fake_twilio.sent == []


async def test_owner_reply_blocks_cross_tenant(client, business, db, fake_twilio):
    # A conversation belonging to a DIFFERENT business ; the test client is authenticated as business.id, so this must 404.
    other_biz = Business(
        name="Other Co", twilio_number="+15559998888",
        owner_auth0_id="other|user",
    )
    db.add(other_biz)
    await db.flush()
    other_cust = Customer(business_id=other_biz.id, name="Stranger", phone="+15557770000")
    db.add(other_cust)
    await db.flush()
    other_conv = Conversation(customer_id=other_cust.id, channel="sms")
    db.add(other_conv)
    await db.commit()

    r = await client.post(f"/conversations/{other_conv.id}/messages", json={"body": "hi"})
    assert r.status_code == 404
    assert fake_twilio.sent == []


async def test_daily_cap_query_uses_correct_joins(business, db):
    """
    Regression test for the bug where `_over_daily_cap` queried
    `Conversation.business_id` (which doesn't exist) instead of joining
    through Customer. That bug crashed every voice + SMS webhook with
    `AttributeError: type object 'Conversation' has no attribute 'business_id'`
    in production before any LLM call could happen.
    """
    from app.routes.webhooks import _over_daily_cap

    # No messages at all → under cap.
    assert await _over_daily_cap(db, business.id) is False

    # Add one inbound message via the conversation graph and re check.
    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id).limit(1)
    )).scalar_one()
    conv = Conversation(customer_id=cust.id, channel="sms")
    db.add(conv)
    await db.flush()
    db.add(Message(conversation_id=conv.id, direction=MessageDirection.inbound, body="hi"))
    await db.commit()

    # Still under the default 500/day cap ; but the query itself must execute without raising. That's the regression guard.
    assert await _over_daily_cap(db, business.id) is False


async def test_owner_reply_rejects_empty_body(client, business, db, fake_twilio):
    cust = (await db.execute(
        select(Customer).where(Customer.business_id == business.id).limit(1)
    )).scalar_one()
    conv = Conversation(customer_id=cust.id, channel="sms")
    db.add(conv)
    await db.commit()

    r = await client.post(f"/conversations/{conv.id}/messages", json={"body": "   "})
    assert r.status_code == 422
    assert fake_twilio.sent == []
