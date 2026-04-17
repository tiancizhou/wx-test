from sqlalchemy import select
import pytest

from models import Consultation


@pytest.mark.asyncio
async def test_seeded_data_and_async_client_are_available(
    client,
    seeded_session,
    auth_headers,
    customer_user,
    merchant_user,
    seeded_good,
):
    response = await client.get("/goods")

    assert response.status_code == 200
    goods = response.json()
    assert any(item["id"] == seeded_good.id for item in goods)

    me_response = await client.get("/me", headers=auth_headers)
    assert me_response.status_code == 200
    assert me_response.json()["openid"] == customer_user.openid

    consult_response = await client.post("/consult", json={"good_id": seeded_good.id}, headers=auth_headers)
    assert consult_response.status_code == 200

    consult_id = int(consult_response.json()["thread_id"])
    consult = (
        await seeded_session.execute(select(Consultation).where(Consultation.id == consult_id))
    ).scalar_one()

    assert consult.customer_id == customer_user.id
    assert consult.good_id == seeded_good.id
    assert merchant_user.role == "MERCHANT"
