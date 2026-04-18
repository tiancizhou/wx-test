import pytest

from models import Order


@pytest.mark.asyncio
async def test_merchant_conversation_list_shows_unread_counts(
    client,
    seeded_session,
    auth_headers,
    merchant_headers,
    customer_user,
    seeded_good,
):
    order = Order(
        customer_id=customer_user.id,
        good_id=seeded_good.id,
        phone="13800000000",
        address="",
        appointment_time="2026-04-18 16:00",
        total_fee=19900,
        quantity=1,
        status=1,
    )
    seeded_session.add(order)
    await seeded_session.commit()
    await seeded_session.refresh(order)

    await client.post(
        "/conversation/messages",
        json={"message_type": "text", "content": "你好，我想确认预约"},
        headers=auth_headers,
    )

    response = await client.get("/merchant/conversations", headers=merchant_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["customer_id"] == customer_user.id
    assert body[0]["unread_count"] == 1
    assert body[0]["last_message_preview"] == "你好，我想确认预约"


@pytest.mark.asyncio
async def test_merchant_can_reply_and_mark_read(
    client,
    auth_headers,
    merchant_headers,
):
    summary = await client.get("/conversation", headers=auth_headers)
    conversation_id = summary.json()["conversation_id"]
    await client.post(
        "/conversation/messages",
        json={"message_type": "text", "content": "客户先发一句"},
        headers=auth_headers,
    )

    reply = await client.post(
        f"/merchant/conversations/{conversation_id}/messages",
        json={"message_type": "text", "content": "商家已收到"},
        headers=merchant_headers,
    )
    assert reply.status_code == 200
    assert reply.json()["sender_role"] == "MERCHANT"
    assert reply.json()["merchant_contact_name"] == "商家A"

    read = await client.post(
        f"/merchant/conversations/{conversation_id}/read",
        json={"last_message_id": reply.json()["id"]},
        headers=merchant_headers,
    )
    assert read.status_code == 200
    assert read.json() == {"ok": True}


@pytest.mark.asyncio
async def test_merchant_can_send_order_card_for_current_customer(
    client,
    seeded_session,
    auth_headers,
    merchant_headers,
    customer_user,
    seeded_good,
):
    order = Order(
        customer_id=customer_user.id,
        good_id=seeded_good.id,
        phone="13800000000",
        address="",
        appointment_time="2026-04-18 18:00",
        total_fee=19900,
        quantity=1,
        status=1,
    )
    seeded_session.add(order)
    await seeded_session.commit()
    await seeded_session.refresh(order)

    summary = await client.get("/conversation", headers=auth_headers)
    conversation_id = summary.json()["conversation_id"]

    response = await client.post(
        f"/merchant/conversations/{conversation_id}/messages",
        json={"message_type": "order_card", "order_id": order.id},
        headers=merchant_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message_type"] == "order_card"
    assert body["order_id"] == order.id
    assert body["payload"]["good_title"] == seeded_good.title
    assert body["merchant_contact_name"] == "商家A"


@pytest.mark.asyncio
async def test_merchant_read_rejects_message_ids_outside_conversation(
    client,
    auth_headers,
    merchant_headers,
):
    summary = await client.get("/conversation", headers=auth_headers)
    conversation_id = summary.json()["conversation_id"]
    await client.post(
        "/conversation/messages",
        json={"message_type": "text", "content": "客户发来第一条"},
        headers=auth_headers,
    )

    invalid_read = await client.post(
        f"/merchant/conversations/{conversation_id}/read",
        json={"last_message_id": 999999},
        headers=merchant_headers,
    )
    assert invalid_read.status_code == 400

    unread = await client.get("/merchant/conversations", headers=merchant_headers)
    assert unread.status_code == 200
    assert unread.json()[0]["unread_count"] == 1
