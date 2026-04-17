import pytest


@pytest.mark.asyncio
async def test_seeded_data_and_async_client_are_available(client, customer_user, merchant_user, seeded_good):
    response = await client.get("/goods")

    assert response.status_code == 200
    goods = response.json()
    assert any(item["id"] == seeded_good.id for item in goods)
    assert customer_user.role == "CUSTOMER"
    assert merchant_user.role == "MERCHANT"
