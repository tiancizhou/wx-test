from sqlalchemy import select
import pytest

from models import Conversation, Order


@pytest.mark.asyncio
async def test_get_conversation_auto_creates_customer_conversation(
    client,
    seeded_session,
    auth_headers,
    customer_user,
):
    response = await client.get("/conversation", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == customer_user.id
    assert body["unread_count"] == 0
    assert body["default_merchant_contact"]["name"] == "客服A"

    conversation = (
        await seeded_session.execute(
            select(Conversation).where(Conversation.customer_id == customer_user.id)
        )
    ).scalar_one()
    assert conversation.default_merchant_contact_id is not None


@pytest.mark.asyncio
async def test_customer_can_send_text_and_order_card_messages(
    client,
    seeded_session,
    auth_headers,
    customer_user,
    seeded_good,
):
    order = Order(
        customer_id=customer_user.id,
        good_id=seeded_good.id,
        phone="13800000000",
        address="",
        appointment_time="2026-04-18 14:00",
        total_fee=19900,
        quantity=1,
        status=1,
    )
    seeded_session.add(order)
    await seeded_session.commit()
    await seeded_session.refresh(order)

    summary = await client.get("/conversation", headers=auth_headers)
    conversation_id = summary.json()["conversation_id"]

    text_response = await client.post(
        "/conversation/messages",
        json={"message_type": "text", "content": "想确认下到店时间"},
        headers=auth_headers,
    )
    assert text_response.status_code == 200
    assert text_response.json()["conversation_id"] == conversation_id
    assert text_response.json()["message_type"] == "text"

    order_response = await client.post(
        "/conversation/messages",
        json={"message_type": "order_card", "order_id": order.id},
        headers=auth_headers,
    )
    assert order_response.status_code == 200
    assert order_response.json()["message_type"] == "order_card"
    assert order_response.json()["payload"]["good_title"] == seeded_good.title
    assert order_response.json()["payload"]["appointment_time"] == "2026-04-18 14:00"

    messages = await client.get("/conversation/messages?after_id=0", headers=auth_headers)
    assert messages.status_code == 200
    assert [item["message_type"] for item in messages.json()] == ["text", "order_card"]


@pytest.mark.asyncio
async def test_customer_can_switch_default_contact_and_mark_read(
    client,
    auth_headers,
    merchant_contacts,
):
    await client.get("/conversation", headers=auth_headers)

    switch_response = await client.post(
        "/conversation/default-contact",
        json={"merchant_contact_id": merchant_contacts[1].id},
        headers=auth_headers,
    )
    assert switch_response.status_code == 200
    assert switch_response.json()["default_merchant_contact"]["id"] == merchant_contacts[1].id

    sent = await client.post(
        "/conversation/messages",
        json={"message_type": "text", "content": "改由客服B接待"},
        headers=auth_headers,
    )
    assert sent.status_code == 200
    assert sent.json()["merchant_contact_id"] == merchant_contacts[1].id
    assert sent.json()["merchant_contact_name"] == merchant_contacts[1].name

    read_response = await client.post(
        "/conversation/read",
        json={"last_message_id": sent.json()["id"]},
        headers=auth_headers,
    )
    assert read_response.status_code == 200
    assert read_response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_message_level_contact_name_is_preserved_after_switching_default_contact(
    client,
    auth_headers,
    merchant_contacts,
):
    await client.get("/conversation", headers=auth_headers)

    first = await client.post(
        "/conversation/messages",
        json={"message_type": "text", "content": "先由客服A处理"},
        headers=auth_headers,
    )
    assert first.status_code == 200
    assert first.json()["merchant_contact_name"] == merchant_contacts[0].name

    switched = await client.post(
        "/conversation/default-contact",
        json={"merchant_contact_id": merchant_contacts[1].id},
        headers=auth_headers,
    )
    assert switched.status_code == 200

    second = await client.post(
        "/conversation/messages",
        json={"message_type": "text", "content": "再由客服B处理"},
        headers=auth_headers,
    )
    assert second.status_code == 200
    assert second.json()["merchant_contact_name"] == merchant_contacts[1].name

    messages = await client.get("/conversation/messages?after_id=0", headers=auth_headers)
    assert messages.status_code == 200
    body = messages.json()
    assert [item["merchant_contact_name"] for item in body] == [
        merchant_contacts[0].name,
        merchant_contacts[1].name,
    ]
