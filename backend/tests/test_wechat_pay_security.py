import base64
import json
import time

import pytest
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

import wechat.pay as pay_module
from wechat.config import settings


@pytest.fixture(autouse=True)
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


def _build_encrypted_callback_body(api_v3_key: str, resource_payload: dict) -> str:
    nonce = "callbacknonce"
    associated_data = "transaction"
    cipher = AES.new(api_v3_key.encode("utf-8"), AES.MODE_GCM, nonce=nonce.encode("utf-8"))
    cipher.update(associated_data.encode("utf-8"))
    ciphertext, tag = cipher.encrypt_and_digest(
        json.dumps(resource_payload, separators=(",", ":")).encode("utf-8")
    )

    body = {
        "id": "EV-20260417-0001",
        "event_type": "TRANSACTION.SUCCESS",
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


def test_mock_mode_skips_payment_config_validation(monkeypatch):
    monkeypatch.setattr(settings, "PAY_MOCK", True)
    monkeypatch.setattr(settings, "MCH_ID", "")
    monkeypatch.setattr(settings, "MCH_SERIAL_NO", "")
    monkeypatch.setattr(settings, "MCH_PRIVATE_KEY_PATH", "")
    monkeypatch.setattr(settings, "API_V3_KEY", "")
    monkeypatch.setattr(settings, "PLATFORM_SERIAL_NO", "", raising=False)
    monkeypatch.setattr(settings, "PLATFORM_PUBLIC_KEY_PATH", "", raising=False)

    settings.validate_payment_config(require_platform_public_key=True)


def test_prod_mode_requires_payment_key_fields(monkeypatch):
    monkeypatch.setattr(settings, "PAY_MOCK", False)
    monkeypatch.setattr(settings, "MCH_ID", "")
    monkeypatch.setattr(settings, "PLATFORM_PUBLIC_KEY_PATH", "", raising=False)

    with pytest.raises(RuntimeError, match=r"WX_MCH_ID.*WX_PLATFORM_PUBLIC_KEY_PATH"):
        settings.validate_payment_config(require_platform_public_key=True)


def test_verify_pay_notify_rejects_stale_timestamp(payment_security_config):
    body = _build_encrypted_callback_body(
        settings.API_V3_KEY,
        {
            "out_trade_no": "ORDER-ST123",
            "trade_state": "SUCCESS",
            "transaction_id": "4200000000000000001",
        },
    )
    timestamp = str(int(time.time()) - 601)
    nonce = "stale-nonce-001"
    signature = _sign_callback(payment_security_config["platform_private_key"], timestamp, nonce, body)

    assert (
        pay_module.verify_pay_notify(
            timestamp,
            nonce,
            body,
            signature,
            wechatpay_serial=payment_security_config["platform_serial"],
        )
        is None
    )


def test_verify_pay_notify_accepts_valid_signed_and_encrypted_callback(payment_security_config):
    expected_resource = {
        "out_trade_no": "ORDER-OK123",
        "trade_state": "SUCCESS",
        "transaction_id": "4200000000000000002",
        "amount": {"total": 19900},
    }
    body = _build_encrypted_callback_body(settings.API_V3_KEY, expected_resource)
    timestamp = str(int(time.time()))
    nonce = "fresh-nonce-001"
    signature = _sign_callback(payment_security_config["platform_private_key"], timestamp, nonce, body)

    result = pay_module.verify_pay_notify(
        timestamp,
        nonce,
        body,
        signature,
        wechatpay_serial=payment_security_config["platform_serial"],
    )

    assert result == {"event_type": "TRANSACTION.SUCCESS", "resource": expected_resource}
