import pytest
from sqlalchemy import select

import main as main_module
from models import Order, OrderStatus
from wechat.config import settings


@pytest.fixture(autouse=True)
def mock_payment_mode(monkeypatch):
    monkeypatch.setattr(settings, "PAY_MOCK", True)


async def _create_order(client, seeded_good, auth_headers, quantity=1):
    response = await client.post(
        "/pay/create",
        json={
            "good_id": seeded_good.id,
            "phone": "13800000000",
            "address": "",
            "appointment_time": "2026-04-18 10:00",
            "quantity": quantity,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_mock_create_keeps_order_unpaid_and_sales_unchanged(
    client,
    seeded_session,
    auth_headers,
    seeded_good,
):
    result = await _create_order(client, seeded_good, auth_headers)

    assert result["mock"] is True
    assert result["status"] == "NOTPAY"

    order = (
        await seeded_session.execute(select(Order).where(Order.id == result["order_id"]))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert order.status == OrderStatus.UNPAID
    assert seeded_good.sales == 0


@pytest.mark.asyncio
async def test_mock_query_returns_notpay_for_unconfirmed_order(
    client,
    auth_headers,
    seeded_good,
):
    result = await _create_order(client, seeded_good, auth_headers)

    response = await client.post(f"/pay/query/{result['order_id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"mock": True, "trade_state": "NOTPAY"}


@pytest.mark.asyncio
async def test_mock_confirm_marks_order_paid_and_increments_sales(
    client,
    seeded_session,
    auth_headers,
    seeded_good,
):
    result = await _create_order(client, seeded_good, auth_headers, quantity=2)

    response = await client.post(f"/pay/mock/confirm/{result['order_id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"mock": True, "order_id": result["order_id"], "status": "SUCCESS"}

    order = (
        await seeded_session.execute(select(Order).where(Order.id == result["order_id"]))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert order.status == OrderStatus.ORDERED
    assert seeded_good.sales == 2


@pytest.mark.asyncio
async def test_mock_confirm_is_unavailable_when_pay_mock_is_false(
    client,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "PAY_MOCK", False)

    response = await client.post("/pay/mock/confirm/mock-disabled-order", headers=auth_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "仅 mock 模式可用"}


@pytest.mark.asyncio
async def test_mock_query_returns_success_after_mock_confirm(
    client,
    auth_headers,
    seeded_good,
):
    result = await _create_order(client, seeded_good, auth_headers)
    confirm_response = await client.post(f"/pay/mock/confirm/{result['order_id']}", headers=auth_headers)
    assert confirm_response.status_code == 200

    response = await client.post(f"/pay/query/{result['order_id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"mock": True, "trade_state": "SUCCESS"}


@pytest.mark.asyncio
async def test_mock_confirm_rejects_repeated_confirm_for_non_unpaid_order(
    client,
    seeded_session,
    auth_headers,
    seeded_good,
):
    result = await _create_order(client, seeded_good, auth_headers)

    first_response = await client.post(f"/pay/mock/confirm/{result['order_id']}", headers=auth_headers)
    assert first_response.status_code == 200

    response = await client.post(f"/pay/mock/confirm/{result['order_id']}", headers=auth_headers)

    assert response.status_code == 400
    assert response.json() == {"detail": "订单状态不允许确认支付"}

    order = (
        await seeded_session.execute(select(Order).where(Order.id == result["order_id"]))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert order.status == OrderStatus.ORDERED
    assert seeded_good.sales == 1


@pytest.mark.asyncio
async def test_apply_refund_success_rejects_invalid_unpaid_transition(
    seeded_session,
    auth_headers,
    client,
    seeded_good,
):
    result = await _create_order(client, seeded_good, auth_headers)

    with pytest.raises(ValueError, match="订单状态不支持退款成功"):
        await main_module.apply_refund_success(
            result["order_id"],
            seeded_session,
            refund_id="mock-refund-invalid",
        )

    order = (
        await seeded_session.execute(select(Order).where(Order.id == result["order_id"]))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert order.status == OrderStatus.UNPAID
    assert order.refund_id == ""
    assert seeded_good.sales == 0


@pytest.mark.asyncio
async def test_mock_refund_reuses_refund_success_and_marks_order_refunded(
    client,
    seeded_session,
    auth_headers,
    seeded_good,
):
    result = await _create_order(client, seeded_good, auth_headers, quantity=3)
    confirm_response = await client.post(f"/pay/mock/confirm/{result['order_id']}", headers=auth_headers)
    assert confirm_response.status_code == 200

    response = await client.post(f"/pay/refund/{result['order_id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"mock": True, "status": "SUCCESS"}

    order = (
        await seeded_session.execute(select(Order).where(Order.id == result["order_id"]))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert order.status == OrderStatus.REFUNDED
    assert seeded_good.sales == 0
