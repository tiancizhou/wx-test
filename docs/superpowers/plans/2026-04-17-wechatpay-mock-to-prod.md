# WeChat Pay Mock-to-Prod Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current merchant-mode WeChat Pay flow safe for production while preserving a realistic mock checkout flow that can be turned off with configuration only.

**Architecture:** Keep the existing FastAPI routes in `backend/main.py`, but extract shared payment/refund state-transition helpers so mock success and real callbacks update orders through the same code path. Move formal callback hardening into `backend/wechat/config.py` and `backend/wechat/pay.py`: production mode validates required config at startup, callbacks must verify signatures, decrypt the body, validate amount/appid/mchid, then call the shared state-transition helpers.

**Tech Stack:** FastAPI, SQLAlchemy asyncio, SQLite, PyCryptodome, httpx, pytest, pytest-asyncio

---

## File Map

- Modify: `backend/pyproject.toml` — add backend test dependencies.
- Modify: `backend/wechat/config.py` — add platform public-key settings and runtime production validation.
- Modify: `backend/wechat/pay.py` — add platform public-key loading, callback signature verification, and verified decrypt wrappers.
- Modify: `backend/main.py` — add shared payment/refund application helpers, wire startup validation, add mock confirm endpoint, refactor callback routes.
- Modify: `frontend/customer.html` — call the mock confirm endpoint before showing success.
- Create: `backend/tests/conftest.py` — async DB/client fixtures for route tests.
- Create: `backend/tests/test_wechat_pay_security.py` — runtime-config and callback-signature coverage.
- Create: `backend/tests/test_payment_flow.py` — mock create/confirm/query/refund flow coverage.
- Create: `backend/tests/test_payment_callbacks.py` — callback route, idempotency, and field-validation coverage.

---

### Task 1: Add backend test tooling and fixtures

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Add backend dev dependencies**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv add --dev pytest pytest-asyncio
```

Expected `backend/pyproject.toml` diff:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

- [ ] **Step 2: Verify pytest is available**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest --version
```

Expected: prints a pytest version instead of `ModuleNotFoundError`.

- [ ] **Step 3: Create the shared async test harness**

Write `backend/tests/conftest.py`:

```python
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import main
from database import Base
from models import Good, Role, User


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Token": "customer-openid"}


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    db_file = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session(db_session: AsyncSession) -> AsyncIterator[AsyncSession]:
    customer = User(openid="customer-openid", role=Role.CUSTOMER, nickname="测试客户")
    good = Good(title="测试 60 分钟套餐", description="肩颈按摩", price=19900, duration=60, is_active=True)
    db_session.add_all([customer, good])
    await db_session.commit()
    yield db_session


@pytest_asyncio.fixture
async def client(seeded_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_db():
        yield seeded_session

    main.app.dependency_overrides[main.get_db] = override_get_db
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
    main.app.dependency_overrides.clear()
```

- [ ] **Step 4: Smoke-check the test harness**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests -q
```

Expected: pytest starts successfully and reports `no tests ran`.

- [ ] **Step 5: Commit the harness**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add backend/pyproject.toml backend/uv.lock backend/tests/conftest.py && git commit -m "test: add backend payment test harness"
```

---

### Task 2: Add production config validation and callback signature helpers

**Files:**
- Modify: `backend/wechat/config.py`
- Modify: `backend/wechat/pay.py`
- Test: `backend/tests/test_wechat_pay_security.py`

- [ ] **Step 1: Write the failing security tests**

Create `backend/tests/test_wechat_pay_security.py`:

```python
import base64
import json
import time

import pytest
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

import wechat.pay as pay
from wechat.config import settings, validate_pay_runtime_config


def _sign_body(private_key: RSA.RsaKey, body: str, *, timestamp: str, nonce: str) -> str:
    message = f"{timestamp}\n{nonce}\n{body}\n"
    digest = SHA256.new(message.encode("utf-8"))
    signature = pkcs1_15.new(private_key).sign(digest)
    return base64.b64encode(signature).decode("utf-8")


def _encrypt_resource(api_v3_key: str, payload: dict) -> dict:
    nonce = "0123456789ab"
    associated_data = "transaction"
    cipher = AES.new(api_v3_key.encode("utf-8"), AES.MODE_GCM, nonce=nonce.encode("utf-8"))
    cipher.update(associated_data.encode("utf-8"))
    ciphertext, tag = cipher.encrypt_and_digest(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return {
        "algorithm": "AEAD_AES_256_GCM",
        "nonce": nonce,
        "associated_data": associated_data,
        "ciphertext": base64.b64encode(ciphertext + tag).decode("utf-8"),
    }


def test_validate_pay_runtime_config_skips_mock(monkeypatch):
    monkeypatch.setattr(settings, "PAY_MOCK", True)
    monkeypatch.setattr(settings, "MCH_ID", "")
    monkeypatch.setattr(settings, "MCH_SERIAL_NO", "")
    monkeypatch.setattr(settings, "MCH_PRIVATE_KEY_PATH", "")
    monkeypatch.setattr(settings, "API_V3_KEY", "")
    monkeypatch.setattr(settings, "PAY_PLATFORM_PUBLIC_KEY_PATH", "")

    validate_pay_runtime_config()


def test_validate_pay_runtime_config_requires_prod_fields(tmp_path, monkeypatch):
    merchant_key = tmp_path / "merchant.pem"
    merchant_key.write_text(RSA.generate(2048).export_key().decode("utf-8"), encoding="utf-8")

    monkeypatch.setattr(settings, "PAY_MOCK", False)
    monkeypatch.setattr(settings, "MCH_ID", "1900000109")
    monkeypatch.setattr(settings, "MCH_SERIAL_NO", "")
    monkeypatch.setattr(settings, "MCH_PRIVATE_KEY_PATH", str(merchant_key))
    monkeypatch.setattr(settings, "API_V3_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(settings, "PAY_PLATFORM_PUBLIC_KEY_PATH", str(tmp_path / "platform.pem"))

    with pytest.raises(RuntimeError, match="WX_MCH_SERIAL_NO"):
        validate_pay_runtime_config()


def test_verify_notification_signature_rejects_stale_timestamp(tmp_path, monkeypatch):
    key = RSA.generate(2048)
    public_key_path = tmp_path / "platform.pem"
    public_key_path.write_text(key.publickey().export_key().decode("utf-8"), encoding="utf-8")

    monkeypatch.setattr(pay, "_platform_public_key", None)
    monkeypatch.setattr(settings, "PAY_PLATFORM_PUBLIC_KEY_PATH", str(public_key_path))
    monkeypatch.setattr(settings, "PAY_PLATFORM_SERIAL", "serial-123")

    body = '{"id":"evt-1"}'
    timestamp = str(int(time.time()) - 600)
    signature = _sign_body(key, body, timestamp=timestamp, nonce="nonce-1")

    assert not pay.verify_notification_signature(
        timestamp=timestamp,
        nonce="nonce-1",
        body=body,
        signature=signature,
        wechatpay_serial="serial-123",
    )


def test_verify_and_decrypt_pay_notify_accepts_valid_signature(tmp_path, monkeypatch):
    key = RSA.generate(2048)
    public_key_path = tmp_path / "platform.pem"
    public_key_path.write_text(key.publickey().export_key().decode("utf-8"), encoding="utf-8")

    monkeypatch.setattr(pay, "_platform_public_key", None)
    monkeypatch.setattr(settings, "PAY_PLATFORM_PUBLIC_KEY_PATH", str(public_key_path))
    monkeypatch.setattr(settings, "PAY_PLATFORM_SERIAL", "serial-123")
    monkeypatch.setattr(settings, "API_V3_KEY", "0123456789abcdef0123456789abcdef")

    body = json.dumps(
        {
            "id": "evt-1",
            "event_type": "TRANSACTION.SUCCESS",
            "resource": _encrypt_resource(
                settings.API_V3_KEY,
                {
                    "out_trade_no": "202604170001",
                    "transaction_id": "4200000000001",
                    "trade_state": "SUCCESS",
                    "amount": {"total": 19900},
                    "appid": "wx-test-app",
                    "mchid": "1900000109",
                },
            ),
        },
        separators=(",", ":"),
    )
    timestamp = str(int(time.time()))
    signature = _sign_body(key, body, timestamp=timestamp, nonce="nonce-1")

    data = pay.verify_and_decrypt_pay_notify(
        timestamp=timestamp,
        nonce="nonce-1",
        body=body,
        signature=signature,
        wechatpay_serial="serial-123",
    )

    assert data["resource"]["out_trade_no"] == "202604170001"
    assert data["resource"]["amount"]["total"] == 19900
```

- [ ] **Step 2: Run the tests to capture the current failure**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_wechat_pay_security.py -q
```

Expected: failures because `validate_pay_runtime_config`, `verify_notification_signature`, and `verify_and_decrypt_pay_notify` do not exist yet.

- [ ] **Step 3: Implement config validation and verified decrypt helpers**

Update `backend/wechat/config.py`:

```python
import os
from pathlib import Path


class WeChatSettings:
    TOKEN: str = os.getenv("WX_TOKEN", "qq5201314")
    APP_ID: str = os.getenv("WX_APP_ID", "wx9e7f92a7fad7e40f")
    APP_SECRET: str = os.getenv("WX_APP_SECRET", "3fc48aa59710c119b0dab6a8b725163f")
    ENCODING_AES_KEY: str = os.getenv("WX_ENCODING_AES_KEY", "wkTzbshp2Plx5QZ0uQVcKizai5F1ZCoEARuochQUAkQ")
    ADMIN_KEY: str = os.getenv("WX_ADMIN_KEY", "qq5201314")
    MCH_ID: str = os.getenv("WX_MCH_ID", "")
    MCH_SERIAL_NO: str = os.getenv("WX_MCH_SERIAL_NO", "")
    MCH_PRIVATE_KEY_PATH: str = os.getenv("WX_MCH_PRIVATE_KEY_PATH", "")
    API_V3_KEY: str = os.getenv("WX_API_V3_KEY", "")
    PAY_PLATFORM_PUBLIC_KEY_PATH: str = os.getenv("WX_PAY_PLATFORM_PUBLIC_KEY_PATH", "")
    PAY_PLATFORM_SERIAL: str = os.getenv("WX_PAY_PLATFORM_SERIAL", "")
    PAY_MOCK: bool = os.getenv("WX_PAY_MOCK", "true").lower() == "true"


settings = WeChatSettings()


def validate_pay_runtime_config() -> None:
    if settings.PAY_MOCK:
        return

    required = {
        "WX_MCH_ID": settings.MCH_ID,
        "WX_MCH_SERIAL_NO": settings.MCH_SERIAL_NO,
        "WX_MCH_PRIVATE_KEY_PATH": settings.MCH_PRIVATE_KEY_PATH,
        "WX_API_V3_KEY": settings.API_V3_KEY,
        "WX_PAY_PLATFORM_PUBLIC_KEY_PATH": settings.PAY_PLATFORM_PUBLIC_KEY_PATH,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"缺少正式支付配置: {', '.join(missing)}")

    for env_name, file_path in (
        ("WX_MCH_PRIVATE_KEY_PATH", settings.MCH_PRIVATE_KEY_PATH),
        ("WX_PAY_PLATFORM_PUBLIC_KEY_PATH", settings.PAY_PLATFORM_PUBLIC_KEY_PATH),
    ):
        if not Path(file_path).exists():
            raise RuntimeError(f"{env_name} 文件不存在: {file_path}")
```

Update `backend/wechat/pay.py` with the new helpers:

```python
_platform_public_key = None


def _load_platform_public_key():
    global _platform_public_key
    if _platform_public_key is not None:
        return _platform_public_key
    key_path = settings.PAY_PLATFORM_PUBLIC_KEY_PATH
    if not key_path:
        raise RuntimeError("未配置微信支付平台公钥路径 (WX_PAY_PLATFORM_PUBLIC_KEY_PATH)")
    pem = Path(key_path).read_text(encoding="utf-8")
    _platform_public_key = RSA.import_key(pem)
    return _platform_public_key


def verify_notification_signature(
    *,
    timestamp: str,
    nonce: str,
    body: str,
    signature: str,
    wechatpay_serial: str = "",
) -> bool:
    if not timestamp or not nonce or not body or not signature:
        return False
    try:
        if abs(int(time.time()) - int(timestamp)) > 300:
            return False
    except ValueError:
        return False

    expected_serial = settings.PAY_PLATFORM_SERIAL
    if expected_serial and wechatpay_serial != expected_serial:
        return False

    message = f"{timestamp}\n{nonce}\n{body}\n"
    digest = SHA256.new(message.encode("utf-8"))
    try:
        pkcs1_15.new(_load_platform_public_key()).verify(digest, base64.b64decode(signature))
    except (ValueError, TypeError):
        return False
    return True


def _verify_and_decrypt_notification(
    *,
    timestamp: str,
    nonce: str,
    body: str,
    signature: str,
    wechatpay_serial: str = "",
) -> dict | None:
    if not verify_notification_signature(
        timestamp=timestamp,
        nonce=nonce,
        body=body,
        signature=signature,
        wechatpay_serial=wechatpay_serial,
    ):
        return None

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None

    resource = data.get("resource", {})
    decrypted = _decrypt_resource(resource) if resource.get("ciphertext") else resource
    if not decrypted:
        return None
    return {"event_type": data.get("event_type"), "resource": decrypted}


def verify_and_decrypt_pay_notify(
    *,
    timestamp: str,
    nonce: str,
    body: str,
    signature: str,
    wechatpay_serial: str = "",
) -> dict | None:
    return _verify_and_decrypt_notification(
        timestamp=timestamp,
        nonce=nonce,
        body=body,
        signature=signature,
        wechatpay_serial=wechatpay_serial,
    )


def verify_and_decrypt_refund_notify(
    *,
    timestamp: str,
    nonce: str,
    body: str,
    signature: str,
    wechatpay_serial: str = "",
) -> dict | None:
    return _verify_and_decrypt_notification(
        timestamp=timestamp,
        nonce=nonce,
        body=body,
        signature=signature,
        wechatpay_serial=wechatpay_serial,
    )
```

- [ ] **Step 4: Run the security tests again**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_wechat_pay_security.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit the security helpers**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add backend/wechat/config.py backend/wechat/pay.py backend/tests/test_wechat_pay_security.py && git commit -m "fix: validate payment config and callback signatures"
```

---

### Task 3: Unify mock checkout with the real payment success flow

**Files:**
- Modify: `backend/main.py:345-565`
- Test: `backend/tests/test_payment_flow.py`

- [ ] **Step 1: Write the failing mock-flow tests**

Create `backend/tests/test_payment_flow.py`:

```python
import pytest

import main
from models import Good, Order, OrderStatus


async def _create_order(client, auth_headers):
    return await client.post(
        "/pay/create",
        headers=auth_headers,
        json={
            "good_id": 1,
            "phone": "13800000000",
            "address": "",
            "quantity": 1,
            "appointment_time": "2026-04-18 09:00-10:00",
        },
    )


@pytest.mark.asyncio
async def test_mock_create_keeps_order_unpaid(client, seeded_session, auth_headers, monkeypatch):
    monkeypatch.setattr(main.settings, "PAY_MOCK", True)

    response = await _create_order(client, auth_headers)
    data = response.json()
    order = await seeded_session.get(Order, data["order_id"])

    assert response.status_code == 200
    assert data["mock"] is True
    assert order.status == OrderStatus.UNPAID


@pytest.mark.asyncio
async def test_mock_confirm_marks_order_paid(client, seeded_session, auth_headers, monkeypatch):
    monkeypatch.setattr(main.settings, "PAY_MOCK", True)

    create = await _create_order(client, auth_headers)
    order_id = create.json()["order_id"]
    confirm = await client.post(f"/pay/mock/confirm/{order_id}", headers=auth_headers)
    order = await seeded_session.get(Order, order_id)
    good = await seeded_session.get(Good, order.good_id)

    assert confirm.status_code == 200
    assert order.status == OrderStatus.ORDERED
    assert order.transaction_id == f"mock_{order_id}"
    assert good.sales == 1


@pytest.mark.asyncio
async def test_mock_query_tracks_unpaid_and_paid_state(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main.settings, "PAY_MOCK", True)

    create = await _create_order(client, auth_headers)
    order_id = create.json()["order_id"]
    before = await client.post(f"/pay/query/{order_id}", headers=auth_headers)
    await client.post(f"/pay/mock/confirm/{order_id}", headers=auth_headers)
    after = await client.post(f"/pay/query/{order_id}", headers=auth_headers)

    assert before.json()["trade_state"] == "NOTPAY"
    assert after.json()["trade_state"] == "SUCCESS"


@pytest.mark.asyncio
async def test_mock_refund_uses_shared_refund_success_flow(client, seeded_session, auth_headers, monkeypatch):
    monkeypatch.setattr(main.settings, "PAY_MOCK", True)

    create = await _create_order(client, auth_headers)
    order_id = create.json()["order_id"]
    await client.post(f"/pay/mock/confirm/{order_id}", headers=auth_headers)
    refund = await client.post(f"/pay/refund/{order_id}", headers=auth_headers, json={})
    order = await seeded_session.get(Order, order_id)
    good = await seeded_session.get(Good, order.good_id)

    assert refund.status_code == 200
    assert refund.json()["status"] == "SUCCESS"
    assert order.status == OrderStatus.REFUNDED
    assert good.sales == 0
```

- [ ] **Step 2: Run the mock-flow tests and confirm the existing behavior fails**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_payment_flow.py -q
```

Expected: failures because `/pay/create` currently marks orders as paid immediately, `/pay/mock/confirm/{order_id}` does not exist, `/pay/query` always returns `SUCCESS`, and mock refund never reaches `REFUNDED`.

- [ ] **Step 3: Refactor the backend mock flow around shared state helpers**

Update `backend/main.py` with the shared helpers and route changes:

```python
async def apply_payment_success(
    db: AsyncSession,
    *,
    order_id: str,
    transaction_id: str,
    paid_amount: int,
    appid: str,
    mchid: str,
):
    result = await db.execute(select(Order).where(Order.id == order_id).options(selectinload(Order.good)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != OrderStatus.UNPAID:
        return order
    if paid_amount != order.total_fee:
        raise HTTPException(400, "支付金额不一致")
    if appid != settings.APP_ID:
        raise HTTPException(400, "AppID 不匹配")
    if mchid != settings.MCH_ID:
        raise HTTPException(400, "商户号不匹配")

    order.status = OrderStatus.ORDERED
    order.transaction_id = transaction_id
    if order.good:
        await db.execute(
            update(Good).where(Good.id == order.good_id).values(sales=Good.sales + (order.quantity or 1))
        )
    await db.commit()
    return order


async def apply_refund_success(db: AsyncSession, *, order_id: str, refund_id: str):
    result = await db.execute(select(Order).where(Order.id == order_id).options(selectinload(Order.good)))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status == OrderStatus.REFUNDED:
        return order

    order.status = OrderStatus.REFUNDED
    order.refund_id = refund_id
    if order.good:
        qty = order.quantity or 1
        await db.execute(update(Good).where(Good.id == order.good_id).values(sales=max(0, order.good.sales - qty)))
    await db.commit()
    return order


@app.post("/pay/create")
async def pay_create(...):
    ...
    if settings.PAY_MOCK:
        return {"mock": True, "order_id": order.id, "status": "UNPAID"}
    ...


@app.post("/pay/mock/confirm/{order_id}")
async def pay_mock_confirm(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not settings.PAY_MOCK:
        raise HTTPException(404, "mock 支付未启用")
    order = await _verify_order_access(order_id, user, db)
    if order.status != OrderStatus.UNPAID:
        raise HTTPException(400, "订单状态不允许模拟支付")

    await apply_payment_success(
        db,
        order_id=order.id,
        transaction_id=f"mock_{order.id}",
        paid_amount=order.total_fee,
        appid=settings.APP_ID,
        mchid=settings.MCH_ID,
    )
    return {"mock": True, "status": "SUCCESS", "order_id": order.id}


@app.post("/pay/query/{order_id}")
async def pay_query(...):
    order = await _verify_order_access(order_id, user, db)
    if settings.PAY_MOCK:
        trade_state = "SUCCESS" if order.status != OrderStatus.UNPAID else "NOTPAY"
        return {"mock": True, "trade_state": trade_state}
    ...


@app.post("/pay/refund/{order_id}")
async def pay_refund(...):
    ...
    if settings.PAY_MOCK:
        refund_id = f"mock_refund_{order.id}"
        await apply_refund_success(db, order_id=order.id, refund_id=refund_id)
        return {"mock": True, "status": "SUCCESS", "refund_id": refund_id}
    ...
```

- [ ] **Step 4: Re-run the mock-flow tests**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_payment_flow.py -q
```

Expected: all four tests pass.

- [ ] **Step 5: Commit the mock-flow refactor**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add backend/main.py backend/tests/test_payment_flow.py && git commit -m "fix: unify mock and real payment success flow"
```

---

### Task 4: Harden callback routes and startup validation

**Files:**
- Modify: `backend/main.py:50-92` and `backend/main.py:409-565`
- Test: `backend/tests/test_payment_callbacks.py`

- [ ] **Step 1: Write the failing callback tests**

Create `backend/tests/test_payment_callbacks.py`:

```python
import pytest
from fastapi import HTTPException

import main
from models import Good, Order, OrderStatus


async def _insert_unpaid_order(session):
    order = Order(
        customer_id=1,
        good_id=1,
        phone="13800000000",
        address="",
        appointment_time="2026-04-18 09:00-10:00",
        quantity=1,
        total_fee=19900,
        status=OrderStatus.UNPAID,
    )
    session.add(order)
    await session.commit()
    return order.id


@pytest.mark.asyncio
async def test_apply_payment_success_validates_amount_appid_and_mchid(seeded_session, monkeypatch):
    monkeypatch.setattr(main.settings, "APP_ID", "wx-test-app")
    monkeypatch.setattr(main.settings, "MCH_ID", "1900000109")
    order_id = await _insert_unpaid_order(seeded_session)

    with pytest.raises(HTTPException, match="支付金额不一致"):
        await main.apply_payment_success(
            seeded_session,
            order_id=order_id,
            transaction_id="4200000000001",
            paid_amount=29900,
            appid="wx-test-app",
            mchid="1900000109",
        )

    with pytest.raises(HTTPException, match="AppID"):
        await main.apply_payment_success(
            seeded_session,
            order_id=order_id,
            transaction_id="4200000000001",
            paid_amount=19900,
            appid="wrong-appid",
            mchid="1900000109",
        )

    with pytest.raises(HTTPException, match="商户号"):
        await main.apply_payment_success(
            seeded_session,
            order_id=order_id,
            transaction_id="4200000000001",
            paid_amount=19900,
            appid="wx-test-app",
            mchid="wrong-mchid",
        )


@pytest.mark.asyncio
async def test_pay_notify_is_idempotent(client, seeded_session, monkeypatch):
    monkeypatch.setattr(main.settings, "APP_ID", "wx-test-app")
    monkeypatch.setattr(main.settings, "MCH_ID", "1900000109")
    order_id = await _insert_unpaid_order(seeded_session)
    monkeypatch.setattr(
        main,
        "verify_and_decrypt_pay_notify",
        lambda **_: {
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "out_trade_no": order_id,
                "transaction_id": "4200000000001",
                "trade_state": "SUCCESS",
                "amount": {"total": 19900},
                "appid": "wx-test-app",
                "mchid": "1900000109",
            },
        },
    )

    headers = {
        "Wechatpay-Timestamp": "1713320000",
        "Wechatpay-Nonce": "nonce-1",
        "Wechatpay-Signature": "signature",
        "Wechatpay-Serial": "serial-1",
    }
    first = await client.post("/pay/notify", headers=headers, content="{}")
    second = await client.post("/pay/notify", headers=headers, content="{}")
    order = await seeded_session.get(Order, order_id)
    good = await seeded_session.get(Good, order.good_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert order.status == OrderStatus.ORDERED
    assert order.transaction_id == "4200000000001"
    assert good.sales == 1


@pytest.mark.asyncio
async def test_pay_notify_returns_400_when_verification_fails(client, monkeypatch):
    monkeypatch.setattr(main, "verify_and_decrypt_pay_notify", lambda **_: None)

    response = await client.post(
        "/pay/notify",
        headers={
            "Wechatpay-Timestamp": "1713320000",
            "Wechatpay-Nonce": "nonce-1",
            "Wechatpay-Signature": "signature",
            "Wechatpay-Serial": "serial-1",
        },
        content="{}",
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_refund_notify_marks_order_refunded_once(client, seeded_session, monkeypatch):
    monkeypatch.setattr(main.settings, "APP_ID", "wx-test-app")
    monkeypatch.setattr(main.settings, "MCH_ID", "1900000109")
    order_id = await _insert_unpaid_order(seeded_session)
    await main.apply_payment_success(
        seeded_session,
        order_id=order_id,
        transaction_id="4200000000001",
        paid_amount=19900,
        appid="wx-test-app",
        mchid="1900000109",
    )
    monkeypatch.setattr(
        main,
        "verify_and_decrypt_refund_notify",
        lambda **_: {
            "event_type": "REFUND.SUCCESS",
            "resource": {
                "out_trade_no": order_id,
                "refund_id": "500000000001",
                "refund_status": "SUCCESS",
            },
        },
    )

    response = await client.post(
        "/refund/notify",
        headers={
            "Wechatpay-Timestamp": "1713320000",
            "Wechatpay-Nonce": "nonce-1",
            "Wechatpay-Signature": "signature",
            "Wechatpay-Serial": "serial-1",
        },
        content="{}",
    )
    order = await seeded_session.get(Order, order_id)
    good = await seeded_session.get(Good, order.good_id)

    assert response.status_code == 200
    assert order.status == OrderStatus.REFUNDED
    assert order.refund_id == "500000000001"
    assert good.sales == 0
```

- [ ] **Step 2: Run the callback tests to expose the remaining gaps**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_payment_callbacks.py -q
```

Expected: failures because `lifespan` does not validate production config, the callback routes still import the old helper names, and the routes do not call the shared validation helpers.

- [ ] **Step 3: Wire startup validation and hardened callback routes**

Update the imports and callback handling in `backend/main.py`:

```python
from wechat.config import settings, validate_pay_runtime_config
from wechat.pay import (
    close_order,
    create_prepay_order,
    create_refund,
    generate_jsapi_params,
    query_order,
    verify_and_decrypt_pay_notify,
    verify_and_decrypt_refund_notify,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_pay_runtime_config()
    await init_db()
    task = asyncio.create_task(_cleanup_stale_unpaid_orders())
    yield
    task.cancel()


@app.post("/pay/notify")
async def pay_notify(request: Request, db: AsyncSession = Depends(get_db)):
    body = (await request.body()).decode("utf-8")
    data = verify_and_decrypt_pay_notify(
        timestamp=request.headers.get("Wechatpay-Timestamp", ""),
        nonce=request.headers.get("Wechatpay-Nonce", ""),
        body=body,
        signature=request.headers.get("Wechatpay-Signature", ""),
        wechatpay_serial=request.headers.get("Wechatpay-Serial", ""),
    )
    if not data:
        return JSONResponse({"code": "FAIL", "message": "验签或解密失败"}, status_code=400)
    if data.get("event_type") != "TRANSACTION.SUCCESS":
        return Response(status_code=200)

    resource = data["resource"]
    if resource.get("trade_state") != "SUCCESS":
        return Response(status_code=200)

    await apply_payment_success(
        db,
        order_id=resource.get("out_trade_no", ""),
        transaction_id=resource.get("transaction_id", ""),
        paid_amount=resource.get("amount", {}).get("total", 0),
        appid=resource.get("appid", ""),
        mchid=resource.get("mchid", ""),
    )
    return Response(status_code=200)


@app.post("/refund/notify")
async def refund_notify(request: Request, db: AsyncSession = Depends(get_db)):
    body = (await request.body()).decode("utf-8")
    data = verify_and_decrypt_refund_notify(
        timestamp=request.headers.get("Wechatpay-Timestamp", ""),
        nonce=request.headers.get("Wechatpay-Nonce", ""),
        body=body,
        signature=request.headers.get("Wechatpay-Signature", ""),
        wechatpay_serial=request.headers.get("Wechatpay-Serial", ""),
    )
    if not data:
        return JSONResponse({"code": "FAIL", "message": "验签或解密失败"}, status_code=400)

    resource = data["resource"]
    if resource.get("refund_status") != "SUCCESS":
        return Response(status_code=200)

    await apply_refund_success(
        db,
        order_id=resource.get("out_trade_no", ""),
        refund_id=resource.get("refund_id", ""),
    )
    return Response(status_code=200)
```

- [ ] **Step 4: Re-run callback tests, then the full backend suite**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_payment_callbacks.py -q && uv run pytest tests -q
```

Expected: callback tests pass, then the full backend test suite passes.

- [ ] **Step 5: Commit the callback hardening**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add backend/main.py backend/tests/test_payment_callbacks.py && git commit -m "fix: harden payment and refund callbacks"
```

---

### Task 5: Update the customer page and verify the end-to-end mock flow

**Files:**
- Modify: `frontend/customer.html:633-710`
- Verify: backend test suite and browser mock checkout

- [ ] **Step 1: Update the mock branch in `submitOrder()`**

Replace the current mock-success branch in `frontend/customer.html` with:

```html
if (res.mock) {
  await api(`/pay/mock/confirm/${res.order_id}`, { method: 'POST' });
  showBook.value = false;
  vant.showToast('下单成功');
  await loadOrders();
  activeTab.value = 1;
  return;
}
```

- [ ] **Step 2: Re-run the automated backend checks after the frontend change**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests -q
```

Expected: all backend tests still pass.

- [ ] **Step 3: Verify the browser flow in mock mode**

Start the server in mock mode:

```bash
cd "/Users/bob/projects/wx-test/backend" && WX_PAY_MOCK=true uv run uvicorn main:app --reload
```

Seed a local customer and goods row for the browser session:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run python - <<'PY'
import asyncio
from sqlalchemy import select

from database import async_session, init_db
from models import Good, Role, User

async def main():
    await init_db()
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.openid == "customer-openid"))).scalar_one_or_none()
        if not user:
            db.add(User(openid="customer-openid", role=Role.CUSTOMER, nickname="测试客户"))
        good = (await db.execute(select(Good).where(Good.title == "测试 60 分钟套餐"))).scalar_one_or_none()
        if not good:
            db.add(Good(title="测试 60 分钟套餐", description="测试商品", price=19900, duration=60, is_active=True))
        await db.commit()

asyncio.run(main())
PY
```

Manual browser steps:

1. Open `http://127.0.0.1:8000/customer`.
2. In DevTools Console, run:

```js
localStorage.setItem('wx_token', 'customer-openid');
location.reload();
```

3. Place one mock order.
4. Confirm in Network that the page calls `POST /pay/create` and then `POST /pay/mock/confirm/<order_id>`.
5. Refresh the order list and confirm the new order shows as paid instead of lingering in unpaid state.
6. Trigger refund once and confirm the order ends in refunded state.

If this browser flow is blocked for environment-specific reasons, do not claim the UI path is verified; report the blocker explicitly in the implementation summary.

- [ ] **Step 4: Commit the UI change**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add frontend/customer.html && git commit -m "fix: confirm mock payment from customer page"
```

---

## Final Verification Checklist

- [ ] `cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests -q`
- [ ] `WX_PAY_MOCK=true uv run uvicorn main:app --reload` starts successfully.
- [ ] `WX_PAY_MOCK=false` with missing formal payment env vars fails at startup.
- [ ] Browser mock flow hits `/pay/create` then `/pay/mock/confirm/<order_id>`.
- [ ] Duplicate payment callback notifications do not increment sales twice.
- [ ] Refund callback and mock refund end in `REFUNDED` without taking sales below zero.

---

## Spec Coverage Check

- Shared mock/real success path: covered by Task 3.
- Payment/refund callback signature verification and decrypt flow: covered by Task 2 and Task 4.
- Amount/appid/mchid validation: covered by Task 3 helper implementation and Task 4 tests.
- Production startup validation: covered by Task 2 config helper and Task 4 lifespan wiring.
- Minimal frontend change for mock confirm: covered by Task 5.
