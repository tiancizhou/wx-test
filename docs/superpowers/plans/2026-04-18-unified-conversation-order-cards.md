# Unified Conversation with Order Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace consultation/order chat threads with one customer-to-merchant conversation that supports merchant-contact switching, order-card messages, and in-app unread badges on both customer and merchant sides.

**Architecture:** Keep the current FastAPI + inline Vue structure, but replace the active chat model with four new SQLAlchemy models: `MerchantContact`, `Conversation`, `ConversationMessage`, and `ConversationReadState`. Customer APIs become single-conversation endpoints, merchant APIs become customer-conversation list/detail endpoints, and the frontend switches from thread lists to a unified message stream that can send text or order-card messages.

**Tech Stack:** FastAPI, SQLAlchemy asyncio, SQLite, inline Vue 3, Vant 4, pytest, pytest-asyncio, httpx

---

## File Map

- Modify: `backend/models.py` — add unified conversation/contact models and retire the old chat model from active use.
- Modify: `backend/schemas.py` — add merchant-contact, conversation summary, message create/read, and admin CRUD schemas.
- Modify: `backend/main.py` — add unified conversation helpers and routes, merchant conversation routes, admin merchant-contact CRUD, and simplify `orders/active` back to orders only.
- Modify: `backend/tests/conftest.py` — seed merchant contacts and add admin headers.
- Create: `backend/tests/test_conversation_customer_api.py` — customer conversation creation, send text, send order card, switch contact, and read-state coverage.
- Create: `backend/tests/test_conversation_merchant_api.py` — merchant conversation list/detail/send/read coverage.
- Create: `backend/tests/test_admin_merchant_contacts.py` — admin merchant-contact CRUD coverage.
- Modify: `backend/tests/test_harness_smoke.py` — rewrite the smoke test around the unified conversation API.
- Modify: `frontend/customer.html` — direct single chat view, contact picker, order-card picker, order-detail shortcut, and unread badge based on the unified conversation.
- Modify: `frontend/merchant.html` — customer conversation list, unified message stream, order-card rendering, and contact switching.
- Modify: `frontend/admin.html` — replace the single contact form with merchant-contact list/create/edit/delete flows.

---

### Task 1: Add unified conversation models, schemas, and seeded fixtures

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/schemas.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_conversation_customer_api.py`

- [ ] **Step 1: Write the failing customer conversation bootstrap test**

Create `backend/tests/test_conversation_customer_api.py` with:

```python
from sqlalchemy import select
import pytest

from models import Conversation


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
```

- [ ] **Step 2: Run the bootstrap test and confirm it fails before implementation**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_conversation_customer_api.py::test_get_conversation_auto_creates_customer_conversation -v
```

Expected: FAIL with `404 Not Found` for `GET /conversation` or import errors because `Conversation` is not defined yet.

- [ ] **Step 3: Add the new SQLAlchemy models**

Update `backend/models.py` with these model definitions and keep the existing `Order` model unchanged:

```python
class MerchantContact(Base):
    __tablename__ = "merchant_contacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    wechat: Mapped[str] = mapped_column(String(64), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    default_merchant_contact_id: Mapped[int | None] = mapped_column(ForeignKey("merchant_contacts.id"), nullable=True)
    create_time: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

    customer: Mapped["User"] = relationship()
    default_merchant_contact: Mapped["MerchantContact"] = relationship()


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    sender_id: Mapped[int] = mapped_column(Integer)
    sender_role: Mapped[str] = mapped_column(String(16))
    merchant_contact_id: Mapped[int | None] = mapped_column(ForeignKey("merchant_contacts.id"), nullable=True)
    message_type: Mapped[str] = mapped_column(String(16), default="text")
    content: Mapped[str] = mapped_column(Text, default="")
    order_id: Mapped[str] = mapped_column(String(32), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

    merchant_contact: Mapped["MerchantContact"] = relationship()


class ConversationReadState(Base):
    __tablename__ = "conversation_read_states"
    __table_args__ = (PrimaryKeyConstraint("user_id", "conversation_id", "reader_role"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    reader_role: Mapped[str] = mapped_column(String(16), default="")
    last_read_message_id: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Step 4: Add the new Pydantic schemas and extend `OrderOut` with merchant-side nickname data**

Update `backend/schemas.py` with:

```python
from pydantic import BaseModel, model_validator


class MerchantContactOut(BaseModel):
    id: int
    name: str
    wechat: str
    phone: str
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


class MerchantContactCreate(BaseModel):
    name: str
    wechat: str = ""
    phone: str = ""
    is_active: bool = True
    sort_order: int = 0


class MerchantContactUpdate(BaseModel):
    name: str | None = None
    wechat: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ConversationSummaryOut(BaseModel):
    conversation_id: int
    customer_id: int
    customer_nickname: str = ""
    unread_count: int
    last_message_preview: str = ""
    last_message_time: int = 0
    default_merchant_contact: MerchantContactOut | None = None


class ConversationMessageCreate(BaseModel):
    message_type: str = "text"
    content: str = ""
    order_id: str = ""
    merchant_contact_id: int | None = None

    @model_validator(mode="after")
    def validate_payload(self):
        if self.message_type == "text" and not self.content.strip():
            raise ValueError("文本消息不能为空")
        if self.message_type == "order_card" and not self.order_id:
            raise ValueError("订单卡片必须带 order_id")
        if self.message_type not in {"text", "order_card"}:
            raise ValueError("不支持的消息类型")
        return self


class ConversationMessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    sender_role: str
    merchant_contact_id: int | None = None
    message_type: str
    content: str
    order_id: str = ""
    payload: dict | None = None
    create_time: int


class ConversationReadIn(BaseModel):
    last_message_id: int
```

Also extend `OrderOut`:

```python
class OrderOut(BaseModel):
    ...
    customer_nickname: str = ""
```

- [ ] **Step 5: Seed two merchant contacts and add admin headers for later tests**

Update `backend/tests/conftest.py`:

```python
from models import Good, MerchantContact, Role, User

...
merchant_contact_a = MerchantContact(
    name="客服A",
    wechat="service_a",
    phone="13900000001",
    is_active=True,
    sort_order=10,
)
merchant_contact_b = MerchantContact(
    name="客服B",
    wechat="service_b",
    phone="13900000002",
    is_active=True,
    sort_order=20,
)

session.add_all([customer, merchant, good, merchant_contact_a, merchant_contact_b])
...
session.info["seeded_data"] = {
    "customer": customer,
    "merchant": merchant,
    "good": good,
    "merchant_contacts": [merchant_contact_a, merchant_contact_b],
}

@pytest.fixture
def merchant_contacts(seeded_data):
    return seeded_data["merchant_contacts"]


@pytest.fixture
def admin_headers():
    return {"X-Admin-Key": "qq5201314"}
```

- [ ] **Step 6: Run the bootstrap test again and confirm the data layer now supports the route contract**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_conversation_customer_api.py::test_get_conversation_auto_creates_customer_conversation -v
```

Expected: still FAIL with `404 Not Found`, but model import and table creation should now work; the next task will make the route pass.

- [ ] **Step 7: Commit the model/schema groundwork**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add backend/models.py backend/schemas.py backend/tests/conftest.py backend/tests/test_conversation_customer_api.py && git commit -m "feat: add unified conversation models"
```

---

### Task 2: Implement customer unified conversation APIs

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_conversation_customer_api.py`

- [ ] **Step 1: Add failing tests for text messages, order cards, contact switching, and read state**

Append to `backend/tests/test_conversation_customer_api.py`:

```python
from models import ConversationMessage, Order


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

    read_response = await client.post(
        "/conversation/read",
        json={"last_message_id": sent.json()["id"]},
        headers=auth_headers,
    )
    assert read_response.status_code == 200
    assert read_response.json() == {"ok": True}
```

- [ ] **Step 2: Run the customer API tests and confirm route failures**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_conversation_customer_api.py -v
```

Expected: FAIL with missing `/conversation*` routes.

- [ ] **Step 3: Add customer conversation helper functions to `backend/main.py`**

Add these helpers near the current chat helpers, then remove the old `_verify_thread_access` usage from new code paths:

```python
def _contact_to_out(contact: MerchantContact | None) -> dict | None:
    if not contact:
        return None
    return {
        "id": contact.id,
        "name": contact.name,
        "wechat": contact.wechat,
        "phone": contact.phone,
        "is_active": contact.is_active,
        "sort_order": contact.sort_order,
    }


def _message_preview(message: ConversationMessage | None) -> str:
    if not message:
        return ""
    if message.message_type == "order_card" and message.payload_json:
        payload = json.loads(message.payload_json)
        return f"[订单] {payload['good_title']}"
    return message.content[:50]


async def _first_active_contact(db: AsyncSession) -> MerchantContact | None:
    result = await db.execute(
        select(MerchantContact)
        .where(MerchantContact.is_active == True)
        .order_by(MerchantContact.sort_order.asc(), MerchantContact.id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _ensure_default_contact(conversation: Conversation, db: AsyncSession) -> MerchantContact | None:
    contact = conversation.default_merchant_contact
    if contact and contact.is_active:
        return contact
    fallback = await _first_active_contact(db)
    if fallback and conversation.default_merchant_contact_id != fallback.id:
        conversation.default_merchant_contact_id = fallback.id
        await db.commit()
        await db.refresh(conversation)
    return fallback


async def _get_or_create_customer_conversation(user: User, db: AsyncSession) -> Conversation:
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.default_merchant_contact))
        .where(Conversation.customer_id == user.id)
    )
    conversation = result.scalar_one_or_none()
    if conversation:
        await _ensure_default_contact(conversation, db)
        return conversation

    fallback = await _first_active_contact(db)
    conversation = Conversation(
        customer_id=user.id,
        default_merchant_contact_id=fallback.id if fallback else None,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.default_merchant_contact))
        .where(Conversation.id == conversation.id)
    )
    return result.scalar_one()


async def _build_order_card_payload(order: Order) -> dict:
    return {
        "order_id": order.id,
        "good_title": order.good.title if order.good else "商品",
        "good_img_url": order.good.img_url if order.good else "",
        "total_fee": order.total_fee,
        "appointment_time": order.appointment_time,
        "status": order.status,
        "quantity": order.quantity,
    }


def _message_to_out(message: ConversationMessage) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "sender_role": message.sender_role,
        "merchant_contact_id": message.merchant_contact_id,
        "message_type": message.message_type,
        "content": message.content,
        "order_id": message.order_id,
        "payload": json.loads(message.payload_json) if message.payload_json else None,
        "create_time": message.create_time,
    }
```

- [ ] **Step 4: Add the customer conversation routes**

Insert these routes into `backend/main.py` and keep them on the new model only:

```python
@app.get("/merchant-contacts", response_model=list[MerchantContactOut])
async def get_merchant_contacts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MerchantContact)
        .where(MerchantContact.is_active == True)
        .order_by(MerchantContact.sort_order.asc(), MerchantContact.id.asc())
    )
    return result.scalars().all()


@app.get("/conversation", response_model=ConversationSummaryOut)
async def get_conversation(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = await _get_or_create_customer_conversation(user, db)
    last_message = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.id.desc())
        .limit(1)
    )
    message = last_message.scalar_one_or_none()
    read_state = await db.execute(
        select(ConversationReadState).where(
            ConversationReadState.user_id == user.id,
            ConversationReadState.conversation_id == conversation.id,
            ConversationReadState.reader_role == user.role,
        )
    )
    state = read_state.scalar_one_or_none()
    last_read_id = state.last_read_message_id if state else 0
    unread_count = await db.scalar(
        select(func.count()).select_from(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation.id,
            ConversationMessage.id > last_read_id,
            ConversationMessage.sender_role != user.role,
        )
    )
    return {
        "conversation_id": conversation.id,
        "customer_id": user.id,
        "customer_nickname": user.nickname,
        "unread_count": unread_count or 0,
        "last_message_preview": _message_preview(message),
        "last_message_time": message.create_time if message else 0,
        "default_merchant_contact": _contact_to_out(conversation.default_merchant_contact),
    }


@app.get("/conversation/messages", response_model=list[ConversationMessageOut])
async def get_conversation_messages(
    after_id: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = await _get_or_create_customer_conversation(user, db)
    result = await db.execute(
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation.id,
            ConversationMessage.id > after_id,
        )
        .order_by(ConversationMessage.create_time)
    )
    return [_message_to_out(item) for item in result.scalars().all()]


@app.post("/conversation/messages", response_model=ConversationMessageOut)
async def create_conversation_message(
    data: ConversationMessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = await _get_or_create_customer_conversation(user, db)
    contact = conversation.default_merchant_contact
    if data.merchant_contact_id is not None:
        selected = await db.execute(select(MerchantContact).where(MerchantContact.id == data.merchant_contact_id))
        contact = selected.scalar_one_or_none()
        if not contact or not contact.is_active:
            raise HTTPException(400, "客服不存在或已停用")
    elif not contact:
        contact = await _first_active_contact(db)

    payload_json = ""
    content = data.content.strip()
    order_id = ""
    if data.message_type == "order_card":
        order = await _verify_order_access(data.order_id, user, db)
        payload_json = json.dumps(await _build_order_card_payload(order), ensure_ascii=False)
        order_id = order.id
        content = ""

    message = ConversationMessage(
        conversation_id=conversation.id,
        sender_id=user.id,
        sender_role=user.role,
        merchant_contact_id=contact.id if contact else None,
        message_type=data.message_type,
        content=content,
        order_id=order_id,
        payload_json=payload_json,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return _message_to_out(message)


@app.post("/conversation/default-contact", response_model=ConversationSummaryOut)
async def switch_default_contact(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = await _get_or_create_customer_conversation(user, db)
    result = await db.execute(select(MerchantContact).where(MerchantContact.id == data["merchant_contact_id"]))
    contact = result.scalar_one_or_none()
    if not contact or not contact.is_active:
        raise HTTPException(400, "客服不存在或已停用")
    conversation.default_merchant_contact_id = contact.id
    await db.commit()
    await db.refresh(conversation)
    return {
        "conversation_id": conversation.id,
        "customer_id": user.id,
        "customer_nickname": user.nickname,
        "unread_count": 0,
        "last_message_preview": "",
        "last_message_time": 0,
        "default_merchant_contact": _contact_to_out(contact),
    }


@app.post("/conversation/read")
async def mark_conversation_read(
    data: ConversationReadIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = await _get_or_create_customer_conversation(user, db)
    result = await db.execute(
        select(ConversationReadState).where(
            ConversationReadState.user_id == user.id,
            ConversationReadState.conversation_id == conversation.id,
            ConversationReadState.reader_role == user.role,
        )
    )
    state = result.scalar_one_or_none()
    if state:
        state.last_read_message_id = max(state.last_read_message_id, data.last_message_id)
    else:
        db.add(
            ConversationReadState(
                user_id=user.id,
                conversation_id=conversation.id,
                reader_role=user.role,
                last_read_message_id=data.last_message_id,
            )
        )
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 5: Run the customer API tests and confirm they pass**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_conversation_customer_api.py -v
```

Expected: PASS for the new customer conversation tests.

- [ ] **Step 6: Commit the customer API slice**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add backend/main.py backend/tests/test_conversation_customer_api.py && git commit -m "feat: add customer unified conversation APIs"
```

---

### Task 3: Implement merchant conversation APIs and simplify `orders/active`

**Files:**
- Modify: `backend/main.py`
- Test: `backend/tests/test_conversation_merchant_api.py`
- Modify: `backend/schemas.py`

- [ ] **Step 1: Write the failing merchant conversation tests**

Create `backend/tests/test_conversation_merchant_api.py`:

```python
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

    read = await client.post(
        f"/merchant/conversations/{conversation_id}/read",
        json={"last_message_id": reply.json()["id"]},
        headers=merchant_headers,
    )
    assert read.status_code == 200
    assert read.json() == {"ok": True}
```

- [ ] **Step 2: Run the merchant tests and confirm route failures**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_conversation_merchant_api.py -v
```

Expected: FAIL with missing `/merchant/conversations*` routes.

- [ ] **Step 3: Add merchant conversation helpers and endpoints**

Update `backend/main.py` with:

```python
async def _load_conversation_for_merchant(conversation_id: int, db: AsyncSession) -> Conversation:
    result = await db.execute(
        select(Conversation)
        .options(
            selectinload(Conversation.customer),
            selectinload(Conversation.default_merchant_contact),
        )
        .where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "会话不存在")
    await _ensure_default_contact(conversation, db)
    return conversation


@app.get("/merchant/conversations", response_model=list[ConversationSummaryOut])
async def merchant_conversations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.customer), selectinload(Conversation.default_merchant_contact))
        .order_by(Conversation.create_time.desc())
    )
    items = []
    for conversation in result.scalars().all():
        last_message_result = await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.id.desc())
            .limit(1)
        )
        last_message = last_message_result.scalar_one_or_none()
        read_result = await db.execute(
            select(ConversationReadState).where(
                ConversationReadState.user_id == user.id,
                ConversationReadState.conversation_id == conversation.id,
                ConversationReadState.reader_role == user.role,
            )
        )
        state = read_result.scalar_one_or_none()
        last_read_id = state.last_read_message_id if state else 0
        unread = await db.scalar(
            select(func.count()).select_from(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.id,
                ConversationMessage.id > last_read_id,
                ConversationMessage.sender_role != user.role,
            )
        )
        items.append({
            "conversation_id": conversation.id,
            "customer_id": conversation.customer_id,
            "customer_nickname": conversation.customer.nickname if conversation.customer else "",
            "unread_count": unread or 0,
            "last_message_preview": _message_preview(last_message),
            "last_message_time": last_message.create_time if last_message else 0,
            "default_merchant_contact": _contact_to_out(conversation.default_merchant_contact),
        })
    items.sort(key=lambda item: item["last_message_time"] or 0, reverse=True)
    return items


@app.get("/merchant/conversations/{conversation_id}/messages", response_model=list[ConversationMessageOut])
async def merchant_conversation_messages(
    conversation_id: int,
    after_id: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    conversation = await _load_conversation_for_merchant(conversation_id, db)
    result = await db.execute(
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation.id,
            ConversationMessage.id > after_id,
        )
        .order_by(ConversationMessage.create_time)
    )
    return [_message_to_out(item) for item in result.scalars().all()]


@app.post("/merchant/conversations/{conversation_id}/messages", response_model=ConversationMessageOut)
async def merchant_create_conversation_message(
    conversation_id: int,
    data: ConversationMessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    conversation = await _load_conversation_for_merchant(conversation_id, db)
    contact = conversation.default_merchant_contact
    if data.merchant_contact_id is not None:
        selected = await db.execute(select(MerchantContact).where(MerchantContact.id == data.merchant_contact_id))
        contact = selected.scalar_one_or_none()
        if not contact or not contact.is_active:
            raise HTTPException(400, "客服不存在或已停用")
    if data.message_type == "order_card":
        order = await _verify_order_access(data.order_id, user, db)
        payload_json = json.dumps(await _build_order_card_payload(order), ensure_ascii=False)
        content = ""
        order_id = order.id
    else:
        payload_json = ""
        content = data.content.strip()
        order_id = ""

    message = ConversationMessage(
        conversation_id=conversation.id,
        sender_id=user.id,
        sender_role=user.role,
        merchant_contact_id=contact.id if contact else None,
        message_type=data.message_type,
        content=content,
        order_id=order_id,
        payload_json=payload_json,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return _message_to_out(message)


@app.post("/merchant/conversations/{conversation_id}/read")
async def merchant_mark_conversation_read(
    conversation_id: int,
    data: ConversationReadIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    conversation = await _load_conversation_for_merchant(conversation_id, db)
    result = await db.execute(
        select(ConversationReadState).where(
            ConversationReadState.user_id == user.id,
            ConversationReadState.conversation_id == conversation.id,
            ConversationReadState.reader_role == user.role,
        )
    )
    state = result.scalar_one_or_none()
    if state:
        state.last_read_message_id = max(state.last_read_message_id, data.last_message_id)
    else:
        db.add(
            ConversationReadState(
                user_id=user.id,
                conversation_id=conversation.id,
                reader_role=user.role,
                last_read_message_id=data.last_message_id,
            )
        )
    await db.commit()
    return {"ok": True}


@app.post("/merchant/conversations/{conversation_id}/default-contact", response_model=ConversationSummaryOut)
async def merchant_switch_default_contact(
    conversation_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    conversation = await _load_conversation_for_merchant(conversation_id, db)
    result = await db.execute(select(MerchantContact).where(MerchantContact.id == data["merchant_contact_id"]))
    contact = result.scalar_one_or_none()
    if not contact or not contact.is_active:
        raise HTTPException(400, "客服不存在或已停用")
    conversation.default_merchant_contact_id = contact.id
    await db.commit()
    await db.refresh(conversation)
    return {
        "conversation_id": conversation.id,
        "customer_id": conversation.customer_id,
        "customer_nickname": conversation.customer.nickname if conversation.customer else "",
        "unread_count": 0,
        "last_message_preview": "",
        "last_message_time": 0,
        "default_merchant_contact": _contact_to_out(contact),
    }
```

- [ ] **Step 4: Simplify `GET /orders/active` so the order-management tab no longer mixes in consultations**

Replace the existing implementation with:

```python
@app.get("/orders/active")
async def active_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.good), selectinload(Order.customer))
        .order_by(Order.create_time.desc())
    )
    return [_order_to_out(order) for order in result.scalars().all()]
```

- [ ] **Step 5: Run the merchant tests and confirm they pass**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_conversation_merchant_api.py -v
```

Expected: PASS for the merchant conversation tests.

- [ ] **Step 6: Commit the merchant backend slice**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add backend/main.py backend/schemas.py backend/tests/test_conversation_merchant_api.py && git commit -m "feat: add merchant conversation APIs"
```

---

### Task 4: Add admin merchant-contact CRUD and replace the single-contact admin flow

**Files:**
- Modify: `backend/main.py`
- Modify: `frontend/admin.html`
- Test: `backend/tests/test_admin_merchant_contacts.py`

- [ ] **Step 1: Write the failing admin contact CRUD test**

Create `backend/tests/test_admin_merchant_contacts.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_admin_can_create_update_and_delete_merchant_contacts(client, admin_headers):
    created = await client.post(
        "/admin/merchant-contacts",
        json={
            "name": "夜班客服",
            "wechat": "night_shift",
            "phone": "13900000099",
            "is_active": True,
            "sort_order": 30,
        },
        headers=admin_headers,
    )
    assert created.status_code == 200
    contact_id = created.json()["id"]

    listed = await client.get("/admin/merchant-contacts", headers=admin_headers)
    assert listed.status_code == 200
    assert any(item["id"] == contact_id for item in listed.json())

    updated = await client.put(
        f"/admin/merchant-contacts/{contact_id}",
        json={"name": "夜班客服(调整)", "is_active": False},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "夜班客服(调整)"
    assert updated.json()["is_active"] is False

    deleted = await client.delete(f"/admin/merchant-contacts/{contact_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
```

- [ ] **Step 2: Run the admin test and confirm it fails before the routes exist**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_admin_merchant_contacts.py -v
```

Expected: FAIL with missing `/admin/merchant-contacts` routes.

- [ ] **Step 3: Add admin merchant-contact CRUD routes to `backend/main.py`**

Add these routes near the existing admin endpoints:

```python
@app.get("/admin/merchant-contacts", response_model=list[MerchantContactOut])
async def admin_merchant_contacts(
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: AsyncSession = Depends(get_db),
):
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(401, "管理员密钥错误")
    result = await db.execute(select(MerchantContact).order_by(MerchantContact.sort_order.asc(), MerchantContact.id.asc()))
    return result.scalars().all()


@app.post("/admin/merchant-contacts", response_model=MerchantContactOut)
async def create_merchant_contact(
    data: MerchantContactCreate,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: AsyncSession = Depends(get_db),
):
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(401, "管理员密钥错误")
    contact = MerchantContact(**data.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@app.put("/admin/merchant-contacts/{contact_id}", response_model=MerchantContactOut)
async def update_merchant_contact(
    contact_id: int,
    data: MerchantContactUpdate,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: AsyncSession = Depends(get_db),
):
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(401, "管理员密钥错误")
    result = await db.execute(select(MerchantContact).where(MerchantContact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "客服不存在")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)
    await db.commit()
    await db.refresh(contact)
    return contact


@app.delete("/admin/merchant-contacts/{contact_id}")
async def delete_merchant_contact(
    contact_id: int,
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
    db: AsyncSession = Depends(get_db),
):
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(401, "管理员密钥错误")
    result = await db.execute(select(MerchantContact).where(MerchantContact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(404, "客服不存在")
    await db.delete(contact)
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Replace the single-contact form in `frontend/admin.html` with a contact list and create/edit popup**

Replace the current `contactForm` section with list-based state and actions:

```javascript
const merchantContacts = ref([]);
const showContactForm = ref(false);
const editingContactId = ref(0);
const contactForm = ref({ name: '', wechat: '', phone: '', is_active: true, sort_order: 0 });

async function loadMerchantContacts() {
  merchantContacts.value = await api('/admin/merchant-contacts');
}

function openCreateContact() {
  editingContactId.value = 0;
  contactForm.value = { name: '', wechat: '', phone: '', is_active: true, sort_order: merchantContacts.value.length * 10 + 10 };
  showContactForm.value = true;
}

function openEditContact(contact) {
  editingContactId.value = contact.id;
  contactForm.value = { ...contact };
  showContactForm.value = true;
}

async function saveContact() {
  const method = editingContactId.value ? 'PUT' : 'POST';
  const path = editingContactId.value
    ? `/admin/merchant-contacts/${editingContactId.value}`
    : '/admin/merchant-contacts';
  await api(path, { method, body: JSON.stringify(contactForm.value) });
  showContactForm.value = false;
  await loadMerchantContacts();
}

async function removeContact(contact) {
  await api(`/admin/merchant-contacts/${contact.id}`, { method: 'DELETE' });
  await loadMerchantContacts();
}
```

Template block:

```html
<div style="padding:12px 16px;font-weight:600;font-size:16px;display:flex;justify-content:space-between;align-items:center;">
  <span>商家客服 ({{ merchantContacts.length }})</span>
  <van-button size="small" type="primary" @click="openCreateContact">新增客服</van-button>
</div>
<div v-for="contact in merchantContacts" :key="contact.id" class="user-row">
  <div style="flex:1;">
    <div style="font-weight:600;">{{ contact.name }}</div>
    <div style="font-size:12px;color:#666;">微信号：{{ contact.wechat || '未填' }}</div>
    <div style="font-size:12px;color:#666;">手机号：{{ contact.phone || '未填' }}</div>
  </div>
  <div style="display:flex;gap:6px;">
    <van-button size="mini" @click="openEditContact(contact)">编辑</van-button>
    <van-button size="mini" type="danger" plain @click="removeContact(contact)">删除</van-button>
  </div>
</div>
```

- [ ] **Step 5: Run the admin backend test and a quick manual browser check**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_admin_merchant_contacts.py -v
```

Expected: PASS.

Manual check:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run uvicorn main:app --reload
```

Expected: server starts; in `/admin`, create, edit, and delete a merchant contact successfully.

- [ ] **Step 6: Commit the admin contact-management slice**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add backend/main.py frontend/admin.html backend/tests/test_admin_merchant_contacts.py && git commit -m "feat: manage merchant contacts in admin"
```

---

### Task 5: Rewrite the customer UI around a single conversation and order cards

**Files:**
- Modify: `frontend/customer.html`

- [ ] **Step 1: Replace thread-list state with unified conversation state**

In the `<script>` section, remove `conversations`, `activeConv`, `convMessages`, `convMsgInput`, `showContact`, and `contactInfo`. Replace them with:

```javascript
const conversation = ref(null);
const conversationMessages = ref([]);
const conversationInput = ref('');
const conversationBox = ref(null);
const merchantContacts = ref([]);
const showContactPicker = ref(false);
const showOrderPicker = ref(false);
const selectedOrderList = computed(() => orders.value.filter(o => o.status >= 1));
const unreadCount = computed(() => conversation.value?.unread_count || 0);
```

- [ ] **Step 2: Add customer conversation loaders and send helpers**

Add these functions:

```javascript
async function loadConversationSummary() {
  conversation.value = await api('/conversation');
}

async function loadMerchantContacts() {
  merchantContacts.value = await api('/merchant-contacts');
}

async function loadConversationMessages(afterId = 0) {
  const list = await api(`/conversation/messages?after_id=${afterId}`);
  if (afterId === 0) conversationMessages.value = list;
  else if (list.length) conversationMessages.value.push(...list);
  if (conversationMessages.value.length) {
    await api('/conversation/read', {
      method: 'POST',
      body: JSON.stringify({ last_message_id: conversationMessages.value[conversationMessages.value.length - 1].id }),
    });
    if (conversation.value) conversation.value.unread_count = 0;
  }
  await nextTick();
  if (conversationBox.value) conversationBox.value.scrollTop = conversationBox.value.scrollHeight;
}

async function sendConversationText() {
  if (!conversationInput.value.trim()) return;
  const sent = await api('/conversation/messages', {
    method: 'POST',
    body: JSON.stringify({ message_type: 'text', content: conversationInput.value }),
  });
  conversationInput.value = '';
  conversationMessages.value.push(sent);
  await nextTick();
  if (conversationBox.value) conversationBox.value.scrollTop = conversationBox.value.scrollHeight;
}

async function sendOrderCard(order) {
  const sent = await api('/conversation/messages', {
    method: 'POST',
    body: JSON.stringify({ message_type: 'order_card', order_id: order.id }),
  });
  conversationMessages.value.push(sent);
  showOrderPicker.value = false;
  activeTab.value = 2;
  await nextTick();
  if (conversationBox.value) conversationBox.value.scrollTop = conversationBox.value.scrollHeight;
}

async function switchMerchantContact(contact) {
  const updated = await api('/conversation/default-contact', {
    method: 'POST',
    body: JSON.stringify({ merchant_contact_id: contact.id }),
  });
  conversation.value = { ...conversation.value, ...updated };
  showContactPicker.value = false;
}

async function contactAboutOrder(order) {
  activeTab.value = 2;
  if (!conversation.value) await loadConversationSummary();
  if (!conversationMessages.value.length) await loadConversationMessages(0);
  await sendOrderCard(order);
}

async function openGeneralConversation() {
  activeTab.value = 2;
  if (!conversation.value) await loadConversationSummary();
  if (!conversationMessages.value.length) await loadConversationMessages(0);
}
```

- [ ] **Step 3: Replace the Messages tab template with a direct single-chat view**

Replace the current thread-list tab (`activeConv`) with:

```html
<div v-show="activeTab === 2" class="chat-wrap">
  <div class="detail-header">
    <span style="font-weight:600;color:#ffffff;">{{ conversation?.default_merchant_contact?.name || '联系商家' }}</span>
    <div style="margin-left:auto;display:flex;gap:8px;">
      <van-button size="mini" plain @click="showContactPicker = true">切换客服</van-button>
      <van-button size="mini" type="primary" @click="showOrderPicker = true">发送订单</van-button>
    </div>
  </div>
  <div class="chat-messages" ref="conversationBox">
    <div v-if="!conversationMessages.length" class="empty-state" style="padding:40px 0;">暂无消息</div>
    <template v-for="m in conversationMessages" :key="m.id">
      <div
        v-if="m.message_type === 'text'"
        :class="['bubble', 'chat-bubble-col', m.sender_role === user.role ? 'bubble-right' : 'bubble-left']"
      >
        <div v-if="m.sender_role !== user.role" class="bubble-role">{{ roleLabel(m.sender_role) }}</div>
        <div>{{ m.content }}</div>
        <div class="bubble-time">{{ formatTime(m.create_time) }}</div>
      </div>
      <div
        v-else
        :class="['bubble', 'chat-bubble-col', m.sender_role === user.role ? 'bubble-right' : 'bubble-left']"
      >
        <div v-if="m.sender_role !== user.role" class="bubble-role">{{ roleLabel(m.sender_role) }}</div>
        <div style="font-weight:600;">[订单] {{ m.payload.good_title }}</div>
        <div style="font-size:12px;margin-top:4px;">订单号 {{ m.order_id.slice(-8) }}</div>
        <div style="font-size:12px;">预约：{{ m.payload.appointment_time || '未预约' }}</div>
        <div style="font-size:12px;">金额：¥{{ formatPrice(m.payload.total_fee) }}</div>
        <div class="bubble-time">{{ formatTime(m.create_time) }}</div>
      </div>
    </template>
  </div>
  <div class="chat-input-bar">
    <input v-model="conversationInput" placeholder="输入消息..." @keyup.enter="sendConversationText">
    <button @click="sendConversationText">发送</button>
  </div>
</div>
```

Also add two popups:

```html
<van-popup v-model:show="showContactPicker" position="bottom" round>
  <div style="padding:20px;">
    <div style="font-size:16px;font-weight:600;color:#fff;margin-bottom:12px;">选择客服</div>
    <div v-for="contact in merchantContacts" :key="contact.id" class="order-card" @click="switchMerchantContact(contact)">
      <div class="title-white">{{ contact.name }}</div>
      <div class="single-line-preview">微信：{{ contact.wechat || '未填' }} · 手机：{{ contact.phone || '未填' }}</div>
    </div>
  </div>
</van-popup>

<van-popup v-model:show="showOrderPicker" position="bottom" round>
  <div style="padding:20px;max-height:60vh;overflow-y:auto;">
    <div style="font-size:16px;font-weight:600;color:#fff;margin-bottom:12px;">选择订单</div>
    <div v-for="order in selectedOrderList" :key="order.id" class="order-card" @click="sendOrderCard(order)">
      <div class="row-between">
        <span class="title-white">{{ order.good_title }}</span>
        <span :class="['order-status', statusClass(order.status)]">{{ statusText(order.status) }}</span>
      </div>
      <div class="order-summary-text">订单号 {{ order.id.slice(-8) }} · {{ order.appointment_time }}</div>
      <div class="order-price">¥{{ formatPrice(order.total_fee) }}</div>
    </div>
  </div>
</van-popup>
```

- [ ] **Step 4: Rewire entry points so product/detail/my-page actions open the single conversation**

Make these template changes:

```html
<van-button style="flex:1;" round plain @click="openGeneralConversation">联系商家</van-button>
```

```html
<van-button block round type="primary" plain @click="contactAboutOrder(currentOrder)">联系商家</van-button>
```

```html
<van-cell title="联系商家" is-link @click="openGeneralConversation" />
```

And in `onMounted`/polling logic, replace `loadConversations()` / `pollConvChat()` with:

```javascript
await loadConversationSummary();
await loadMerchantContacts();

async function pollConversation() {
  if (!conversation.value) return;
  const lastId = conversationMessages.value.length ? conversationMessages.value[conversationMessages.value.length - 1].id : 0;
  const newer = await api(`/conversation/messages?after_id=${lastId}`);
  if (newer.length) {
    conversationMessages.value.push(...newer);
    await api('/conversation/read', {
      method: 'POST',
      body: JSON.stringify({ last_message_id: conversationMessages.value[conversationMessages.value.length - 1].id }),
    });
    await nextTick();
    if (conversationBox.value) conversationBox.value.scrollTop = conversationBox.value.scrollHeight;
  } else {
    await loadConversationSummary();
  }
}
```

- [ ] **Step 5: Run backend tests and do a customer-side manual check**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_conversation_customer_api.py tests/test_conversation_merchant_api.py -v
```

Expected: PASS.

Manual check:

1. Open `/customer`
2. 点“消息”直接进入聊天
3. 点订单详情“联系商家”后看到一张新订单卡片
4. 在聊天中再手动发送另一笔订单
5. 切换客服后继续发送文本，确认后续消息归到新客服

- [ ] **Step 6: Commit the customer UI slice**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add frontend/customer.html && git commit -m "feat: unify customer conversation UI"
```

---

### Task 6: Rewrite the merchant UI around customer conversations and order cards

**Files:**
- Modify: `frontend/merchant.html`

- [ ] **Step 1: Replace order-derived conversation state with merchant conversation state**

In the `<script>` section, replace the current `conversations = computed(() => orders.value.filter(...))` chat setup with:

```javascript
const conversations = ref([]);
const currentConversation = ref(null);
const messages = ref([]);
const msgInput = ref('');
const chatBox = ref(null);
const merchantContacts = ref([]);
const showContactPicker = ref(false);
const unreadCount = computed(() => conversations.value.reduce((sum, item) => sum + (item.unread_count || 0), 0));

async function loadConversations() {
  conversations.value = await api('/merchant/conversations');
}

async function loadMerchantContacts() {
  merchantContacts.value = await api('/merchant-contacts');
}
```

- [ ] **Step 2: Add merchant message loading, sending, and read helpers**

```javascript
async function openConversation(conv) {
  currentConversation.value = conv;
  messages.value = await api(`/merchant/conversations/${conv.conversation_id}/messages?after_id=0`);
  if (messages.value.length) {
    await api(`/merchant/conversations/${conv.conversation_id}/read`, {
      method: 'POST',
      body: JSON.stringify({ last_message_id: messages.value[messages.value.length - 1].id }),
    });
    conv.unread_count = 0;
  }
  await nextTick();
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight;
}

async function sendMessage() {
  if (!msgInput.value.trim() || !currentConversation.value) return;
  const sent = await api(`/merchant/conversations/${currentConversation.value.conversation_id}/messages`, {
    method: 'POST',
    body: JSON.stringify({ message_type: 'text', content: msgInput.value }),
  });
  msgInput.value = '';
  messages.value.push(sent);
  await nextTick();
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight;
}

async function switchConversationContact(contact) {
  const updated = await api(`/merchant/conversations/${currentConversation.value.conversation_id}/default-contact`, {
    method: 'POST',
    body: JSON.stringify({ merchant_contact_id: contact.id }),
  });
  currentConversation.value = { ...currentConversation.value, ...updated };
  const idx = conversations.value.findIndex(item => item.conversation_id === updated.conversation_id);
  if (idx >= 0) conversations.value[idx] = { ...conversations.value[idx], ...updated };
  showContactPicker.value = false;
}
```

- [ ] **Step 3: Replace the merchant “沟通” template with a customer conversation list and order-card renderer**

Replace the tab body with:

```html
<div v-show="activeTab === 1" style="padding-bottom:60px;">
  <div v-if="!currentConversation">
    <div style="padding:12px 16px;font-weight:600;font-size:16px;color:var(--text-title);">会话</div>
    <div v-if="!conversations.length" style="text-align:center;padding:60px 0;color:var(--text-secondary);font-size:13px;">暂无会话</div>
    <div v-for="conv in conversations" :key="conv.conversation_id" class="order-card" @click="openConversation(conv)">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="display:flex;align-items:center;gap:6px;min-width:0;flex:1;">
          <span v-if="conv.unread_count" class="unread-badge">{{ conv.unread_count }}</span>
          <span style="font-weight:600;color:var(--text-title);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
            {{ conv.customer_nickname || ('客户 #' + conv.customer_id) }}
          </span>
        </div>
        <span class="conv-time">{{ formatTime(conv.last_message_time) }}</span>
      </div>
      <div class="conv-preview">{{ conv.default_merchant_contact?.name || '未分配客服' }} · {{ conv.last_message_preview }}</div>
    </div>
  </div>
  <div v-else class="chat-wrap">
    <div class="detail-header">
      <span class="back-arrow" @click="currentConversation = null; messages = [];">‹</span>
      <div style="flex:1;">
        <div style="font-weight:600;color:var(--text-title);">{{ currentConversation.customer_nickname || ('客户 #' + currentConversation.customer_id) }}</div>
        <div style="font-size:12px;color:var(--text-secondary);">当前接待：{{ currentConversation.default_merchant_contact?.name || '未分配' }}</div>
      </div>
      <van-button size="mini" plain @click="showContactPicker = true">切换客服</van-button>
    </div>
    <div class="chat-messages" ref="chatBox">
      <div v-if="!messages.length" style="text-align:center;padding:40px 0;color:var(--text-secondary);font-size:13px;">暂无消息</div>
      <template v-for="m in messages" :key="m.id">
        <div v-if="m.message_type === 'text'" :class="['bubble', m.sender_role==='MERCHANT' ? 'bubble-right' : 'bubble-left']" style="display:flex;flex-direction:column;">
          <div class="bubble-role">{{ m.sender_role === 'MERCHANT' ? '商家' : (currentConversation.customer_nickname || '客户') }}</div>
          <div>{{ m.content }}</div>
          <div class="bubble-time">{{ formatTime(m.create_time) }}</div>
        </div>
        <div v-else :class="['bubble', m.sender_role==='MERCHANT' ? 'bubble-right' : 'bubble-left']" style="display:flex;flex-direction:column;">
          <div class="bubble-role">{{ m.sender_role === 'MERCHANT' ? '商家' : (currentConversation.customer_nickname || '客户') }}</div>
          <div style="font-weight:600;">[订单] {{ m.payload.good_title }}</div>
          <div style="font-size:12px;margin-top:4px;">订单号 {{ m.order_id.slice(-8) }}</div>
          <div style="font-size:12px;">预约：{{ m.payload.appointment_time || '未预约' }}</div>
          <div style="font-size:12px;">金额：¥{{ formatPrice(m.payload.total_fee) }}</div>
          <div class="bubble-time">{{ formatTime(m.create_time) }}</div>
        </div>
      </template>
    </div>
    <div class="chat-input-bar">
      <input v-model="msgInput" placeholder="回复客户..." @keyup.enter="sendMessage">
      <button @click="sendMessage">发送</button>
    </div>
  </div>
</div>
```

Also add the contact-switch popup:

```html
<van-popup v-model:show="showContactPicker" position="bottom" round>
  <div style="padding:20px;">
    <div style="font-size:16px;font-weight:600;color:#fff;margin-bottom:12px;">切换接待客服</div>
    <div v-for="contact in merchantContacts" :key="contact.id" class="order-card" @click="switchConversationContact(contact)">
      <div class="title-white">{{ contact.name }}</div>
      <div class="conv-preview">微信：{{ contact.wechat || '未填' }} · 手机：{{ contact.phone || '未填' }}</div>
    </div>
  </div>
</van-popup>
```

- [ ] **Step 4: Keep the merchant order-management tab focused on orders only**

Remove chat-derived fields from the order-management tab and its detail view. In particular, delete uses of `thread_type`, `thread_id`, and the old “进入会话” button:

```html
<span class="order-status" :style="{background: statusColor(detailOrder.status), marginLeft:'auto'}">{{ statusText(detailOrder.status) }}</span>
```

```html
<span class="order-status" :style="{background: statusColor(o.status)}">{{ statusText(o.status) }}</span>
```

This keeps order fulfillment separate from the conversation tab while still allowing order cards inside chat.

- [ ] **Step 5: Run backend tests and do a merchant-side manual check**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests/test_conversation_customer_api.py tests/test_conversation_merchant_api.py tests/test_admin_merchant_contacts.py -v
```

Expected: PASS.

Manual check:

1. Open `/merchant`
2. 在“沟通”Tab 看到按客户聚合的会话列表
3. 进入会话后看到客户文本和订单卡片混排
4. 切换接待客服后继续发送回复
5. 返回列表确认未读数变化正确

- [ ] **Step 6: Commit the merchant UI slice**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add frontend/merchant.html && git commit -m "feat: unify merchant conversation UI"
```

---

### Task 7: Remove legacy consultation flow from active use and run final verification

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/tests/test_harness_smoke.py`
- Modify: `frontend/customer.html`
- Modify: `frontend/merchant.html`

- [ ] **Step 1: Rewrite the smoke test to the new conversation contract**

Replace `backend/tests/test_harness_smoke.py` with:

```python
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
    goods_response = await client.get('/goods')
    assert goods_response.status_code == 200
    assert any(item['id'] == seeded_good.id for item in goods_response.json())

    me_response = await client.get('/me', headers=auth_headers)
    assert me_response.status_code == 200
    assert me_response.json()['openid'] == customer_user.openid

    conversation_response = await client.get('/conversation', headers=auth_headers)
    assert conversation_response.status_code == 200
    assert conversation_response.json()['customer_id'] == customer_user.id

    conversation = (
        await seeded_session.execute(
            select(Conversation).where(Conversation.customer_id == customer_user.id)
        )
    ).scalar_one()
    assert conversation.customer_id == customer_user.id
    assert merchant_user.role == 'MERCHANT'
```

- [ ] **Step 2: Remove old consultation/thread entry points from active code paths**

Delete or stop calling these code paths from `backend/main.py` and both frontends:

```python
@app.post('/consult')
@app.get('/chat/conversations')
@app.get('/chat/{thread_type}/{thread_id}')
@app.post('/chat')
@app.post('/chat/read/{thread_type}/{thread_id}')
```

And remove customer-side calls to:

```javascript
startConsult(...)
openConversation(...)
sendConvMessage(...)
loadConversations(...)
markRead(threadType, threadId)
```

The physical old tables can remain in SQLite, but no active route or UI flow should depend on them anymore.

- [ ] **Step 3: Run the full backend test suite**

Run:

```bash
cd "/Users/bob/projects/wx-test/backend" && uv run pytest tests -v
```

Expected: PASS for the existing payment/config tests plus the new conversation tests.

- [ ] **Step 4: Do the full manual acceptance pass**

Manual checklist:

1. `/admin` 创建两个客服并调整排序
2. `/customer` 进入消息页直接看到统一会话
3. 商品详情点击“联系商家”只打开统一会话，不创建新线程
4. 订单详情点击“联系商家”会自动发送当前订单卡片
5. 聊天中再手动发送另一笔订单卡片
6. `/merchant` 在会话列表中看到该客户，未读数正确
7. 商家回复后客户端角标消失/更新正确
8. 商家切换客服后后续消息归属变更，历史消息不变

- [ ] **Step 5: Commit the cleanup and verification pass**

Run:

```bash
cd "/Users/bob/projects/wx-test" && git add backend/main.py backend/tests/test_harness_smoke.py frontend/customer.html frontend/merchant.html && git commit -m "refactor: remove legacy thread-based chat flow"
```

---

## Self-Review

### Spec coverage

- Single customer conversation: covered by Task 1 and Task 2.
- Merchant contact list and switching: covered by Task 1, Task 2, Task 4, and Task 6.
- Text and order-card messages: covered by Task 2, Task 5, and Task 6.
- Order-detail “contact merchant” shortcut: covered by Task 5.
- Merchant conversation list and unread counts: covered by Task 3 and Task 6.
- In-app unread reminders only: covered by Task 2, Task 3, Task 5, and Task 6.
- Remove old consultation/thread flow from active use: covered by Task 7.

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Every code-changing step includes concrete code blocks.
- Every verification step includes an exact command or explicit manual checklist.

### Type consistency

- Unified backend types use `MerchantContact`, `Conversation`, `ConversationMessage`, and `ConversationReadState` consistently.
- API payloads consistently use `message_type`, `merchant_contact_id`, `conversation_id`, and `last_message_id`.
- Frontend code consistently uses `conversation`, `conversationMessages`, and `currentConversation` instead of mixing old `thread_type/thread_id` state.
