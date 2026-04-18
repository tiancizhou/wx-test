from sqlalchemy import select
import pytest

from models import Conversation


@pytest.mark.asyncio
async def test_seeded_data_and_unified_conversation_are_available(
    client,
    seeded_session,
    auth_headers,
    customer_user,
    merchant_user,
    seeded_good,
):
    goods_response = await client.get("/goods")
    assert goods_response.status_code == 200
    assert any(item["id"] == seeded_good.id for item in goods_response.json())

    me_response = await client.get("/me", headers=auth_headers)
    assert me_response.status_code == 200
    assert me_response.json()["openid"] == customer_user.openid

    conversation_response = await client.get("/conversation", headers=auth_headers)
    assert conversation_response.status_code == 200
    assert conversation_response.json()["customer_id"] == customer_user.id

    conversation = (
        await seeded_session.execute(
            select(Conversation).where(Conversation.customer_id == customer_user.id)
        )
    ).scalar_one()
    assert conversation.customer_id == customer_user.id
    assert merchant_user.role == "MERCHANT"
