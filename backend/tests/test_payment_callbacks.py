import base64
import json
import time

import pytest
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from sqlalchemy import select

import main as main_module
import wechat.pay as pay_module
from models import Order, OrderStatus
from wechat.config import settings


async def _create_unpaid_order(seeded_session, customer_user, seeded_good, quantity=1):
    order = Order(
        customer_id=customer_user.id,
        good_id=seeded_good.id,
        phone="13800000000",
        address="",
        appointment_time="2026-04-18 10:00",
        quantity=quantity,
        total_fee=seeded_good.price * quantity,
        status=OrderStatus.UNPAID,
    )
    seeded_session.add(order)
    await seeded_session.commit()
    await seeded_session.refresh(order)
    return order


async def _mark_order_paid(seeded_session, seeded_good, order, transaction_id="txn-paid"):
    order.status = OrderStatus.ORDERED
    order.transaction_id = transaction_id
    seeded_good.sales = order.quantity or 1
    await seeded_session.commit()
    await seeded_session.refresh(order)
    await seeded_session.refresh(seeded_good)
    return order


@pytest.fixture
def payment_security_config(monkeypatch, tmp_path):
    merchant_private_key = RSA.generate(2048)
    platform_private_key = RSA.generate(2048)

    merchant_private_key_path = tmp_path / "merchant_private_key.pem"
    merchant_private_key_path.write_text(
        merchant_private_key.export_key().decode("utf-8"),
        encoding="utf-8",
    )

    platform_public_key_path = tmp_path / "platform_public_key.pem"
    platform_public_key_path.write_text(
        platform_private_key.publickey().export_key().decode("utf-8"),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "PAY_MOCK", False)
    monkeypatch.setattr(settings, "APP_ID", "wx-task4-appid")
    monkeypatch.setattr(settings, "MCH_ID", "1900000109")
    monkeypatch.setattr(settings, "MCH_SERIAL_NO", "merchant-serial-001")
    monkeypatch.setattr(settings, "MCH_PRIVATE_KEY_PATH", str(merchant_private_key_path))
    monkeypatch.setattr(settings, "API_V3_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(settings, "PLATFORM_SERIAL_NO", "platform-serial-001", raising=False)
    monkeypatch.setattr(settings, "PLATFORM_PUBLIC_KEY_PATH", str(platform_public_key_path), raising=False)
    monkeypatch.setattr(pay_module, "_private_key", None)
    monkeypatch.setattr(pay_module, "_platform_public_key", None, raising=False)

    return {
        "platform_private_key": platform_private_key,
        "platform_serial": "platform-serial-001",
    }


def _build_encrypted_callback_body(api_v3_key: str, resource_payload: dict, event_type: str) -> str:
    nonce = "callbacknonce"
    associated_data = "transaction"
    cipher = AES.new(api_v3_key.encode("utf-8"), AES.MODE_GCM, nonce=nonce.encode("utf-8"))
    cipher.update(associated_data.encode("utf-8"))
    ciphertext, tag = cipher.encrypt_and_digest(
        json.dumps(resource_payload, separators=(",", ":")).encode("utf-8")
    )

    body = {
        "id": f"EV-{event_type}-0001",
        "event_type": event_type,
        "resource_type": "encrypt-resource",
        "resource": {
            "algorithm": "AEAD_AES_256_GCM",
            "ciphertext": base64.b64encode(ciphertext + tag).decode("utf-8"),
            "nonce": nonce,
            "associated_data": associated_data,
        },
    }
    return json.dumps(body, separators=(",", ":"))


def _sign_callback(platform_private_key: RSA.RsaKey, timestamp: str, nonce: str, body: str) -> str:
    message = f"{timestamp}\n{nonce}\n{body}\n"
    digest = SHA256.new(message.encode("utf-8"))
    signature = pkcs1_15.new(platform_private_key).sign(digest)
    return base64.b64encode(signature).decode("utf-8")


def _build_callback_headers(platform_private_key: RSA.RsaKey, serial: str, body: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = "notify-nonce-001"
    signature = _sign_callback(platform_private_key, timestamp, nonce, body)
    return {
        "Wechatpay-Timestamp": timestamp,
        "Wechatpay-Nonce": nonce,
        "Wechatpay-Signature": signature,
        "Wechatpay-Serial": serial,
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "error_match"),
    [
        ({"amount_total": 1}, "金额"),
        ({"appid": "wx-wrong-appid"}, "appid"),
        ({"mchid": "1900000110"}, "mchid"),
    ],
)
async def test_apply_payment_success_validates_callback_fields(
    seeded_session,
    customer_user,
    seeded_good,
    monkeypatch,
    overrides,
    error_match,
):
    monkeypatch.setattr(settings, "APP_ID", "wx-task4-appid")
    monkeypatch.setattr(settings, "MCH_ID", "1900000109")
    order = await _create_unpaid_order(seeded_session, customer_user, seeded_good)

    callback_values = {
        "transaction_id": "txn-validate-001",
        "amount_total": order.total_fee,
        "appid": settings.APP_ID,
        "mchid": settings.MCH_ID,
    }
    callback_values.update(overrides)

    with pytest.raises(ValueError, match=error_match):
        await main_module.apply_payment_success(order.id, seeded_session, **callback_values)

    persisted_order = (
        await seeded_session.execute(select(Order).where(Order.id == order.id))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert persisted_order.status == OrderStatus.UNPAID
    assert persisted_order.transaction_id == ""
    assert seeded_good.sales == 0


@pytest.mark.asyncio
async def test_pay_notify_is_idempotent(
    client,
    seeded_session,
    customer_user,
    seeded_good,
    payment_security_config,
):
    order = await _create_unpaid_order(seeded_session, customer_user, seeded_good, quantity=2)
    order_id = order.id
    body = _build_encrypted_callback_body(
        settings.API_V3_KEY,
        {
            "out_trade_no": order_id,
            "trade_state": "SUCCESS",
            "transaction_id": "4200000000000000002",
            "appid": settings.APP_ID,
            "mchid": settings.MCH_ID,
            "amount": {"total": order.total_fee},
        },
        event_type="TRANSACTION.SUCCESS",
    )
    headers = _build_callback_headers(
        payment_security_config["platform_private_key"],
        payment_security_config["platform_serial"],
        body,
    )

    first_response = await client.post("/pay/notify", content=body, headers=headers)
    second_response = await client.post("/pay/notify", content=body, headers=headers)

    persisted_order = (
        await seeded_session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert persisted_order.status == OrderStatus.ORDERED
    assert persisted_order.transaction_id == "4200000000000000002"
    assert seeded_good.sales == 2


@pytest.mark.asyncio
async def test_pay_notify_returns_400_when_wechatpay_serial_verification_fails(
    client,
    seeded_session,
    customer_user,
    seeded_good,
    payment_security_config,
):
    order = await _create_unpaid_order(seeded_session, customer_user, seeded_good)
    body = _build_encrypted_callback_body(
        settings.API_V3_KEY,
        {
            "out_trade_no": order.id,
            "trade_state": "SUCCESS",
            "transaction_id": "4200000000000000003",
            "appid": settings.APP_ID,
            "mchid": settings.MCH_ID,
            "amount": {"total": order.total_fee},
        },
        event_type="TRANSACTION.SUCCESS",
    )
    headers = _build_callback_headers(
        payment_security_config["platform_private_key"],
        "unexpected-platform-serial",
        body,
    )

    response = await client.post("/pay/notify", content=body, headers=headers)

    persisted_order = (
        await seeded_session.execute(select(Order).where(Order.id == order.id))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert response.status_code == 400
    assert response.json()["code"] == "FAIL"
    assert persisted_order.status == OrderStatus.UNPAID
    assert seeded_good.sales == 0


@pytest.mark.asyncio
async def test_refund_notify_marks_order_refunded_once(
    client,
    seeded_session,
    customer_user,
    seeded_good,
    payment_security_config,
):
    order = await _create_unpaid_order(seeded_session, customer_user, seeded_good, quantity=2)
    order_id = order.id
    await _mark_order_paid(seeded_session, seeded_good, order, transaction_id="txn-before-refund")
    body = _build_encrypted_callback_body(
        settings.API_V3_KEY,
        {
            "out_trade_no": order_id,
            "refund_status": "SUCCESS",
            "refund_id": "refund-success-001",
        },
        event_type="REFUND.SUCCESS",
    )
    headers = _build_callback_headers(
        payment_security_config["platform_private_key"],
        payment_security_config["platform_serial"],
        body,
    )

    first_response = await client.post("/refund/notify", content=body, headers=headers)
    second_response = await client.post("/refund/notify", content=body, headers=headers)

    persisted_order = (
        await seeded_session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert persisted_order.status == OrderStatus.REFUNDED
    assert persisted_order.refund_id == "refund-success-001"
    assert seeded_good.sales == 0


@pytest.mark.asyncio
async def test_refund_notify_returns_400_when_wechatpay_serial_verification_fails(
    client,
    seeded_session,
    customer_user,
    seeded_good,
    payment_security_config,
):
    order = await _create_unpaid_order(seeded_session, customer_user, seeded_good)
    await _mark_order_paid(seeded_session, seeded_good, order)
    body = _build_encrypted_callback_body(
        settings.API_V3_KEY,
        {
            "out_trade_no": order.id,
            "refund_status": "SUCCESS",
            "refund_id": "refund-fail-serial-001",
        },
        event_type="REFUND.SUCCESS",
    )
    headers = _build_callback_headers(
        payment_security_config["platform_private_key"],
        "unexpected-platform-serial",
        body,
    )

    response = await client.post("/refund/notify", content=body, headers=headers)

    persisted_order = (
        await seeded_session.execute(select(Order).where(Order.id == order.id))
    ).scalar_one()
    await seeded_session.refresh(seeded_good)

    assert response.status_code == 400
    assert response.json()["code"] == "FAIL"
    assert persisted_order.status == OrderStatus.ORDERED
    assert persisted_order.refund_id == ""
    assert seeded_good.sales == 1


@pytest.mark.asyncio
async def test_lifespan_fails_startup_when_formal_payment_config_is_missing(monkeypatch):
    async def fake_init_db():
        return None

    class DummyTask:
        def cancel(self):
            return None

    def fake_create_task(coro):
        coro.close()
        return DummyTask()

    monkeypatch.setattr(main_module, "init_db", fake_init_db)
    monkeypatch.setattr(main_module.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(settings, "PAY_MOCK", False)
    monkeypatch.setattr(settings, "MCH_ID", "")
    monkeypatch.setattr(settings, "MCH_SERIAL_NO", "")
    monkeypatch.setattr(settings, "MCH_PRIVATE_KEY_PATH", "")
    monkeypatch.setattr(settings, "API_V3_KEY", "")
    monkeypatch.setattr(settings, "PLATFORM_PUBLIC_KEY_PATH", "", raising=False)

    with pytest.raises(RuntimeError, match="微信支付正式环境缺少必要配置"):
        async with main_module.lifespan(main_module.app):
            pass
