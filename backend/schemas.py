from pydantic import BaseModel, model_validator
from typing import Optional


# ---- Good ----
class GoodOut(BaseModel):
    id: int
    title: str
    description: str
    price: int
    original_price: int
    duration: int
    img_url: str
    is_active: bool
    sales: int
    detail_images: str

    class Config:
        from_attributes = True


class GoodUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    original_price: Optional[int] = None
    duration: Optional[int] = None
    img_url: Optional[str] = None
    is_active: Optional[bool] = None
    sales: Optional[int] = None
    detail_images: Optional[str] = None


class GoodCreate(BaseModel):
    title: str
    description: str = ""
    price: int
    original_price: int = 0
    duration: int = 60
    img_url: str = ""
    sales: int = 0
    detail_images: str = "[]"


# ---- Consultation ----
class ConsultCreate(BaseModel):
    good_id: int


class ConsultationOut(BaseModel):
    thread_type: str = "consultation"
    thread_id: str
    good_id: int
    good_title: str = ""
    good_img_url: str = ""
    create_time: int


# ---- Order ----
class OrderOut(BaseModel):
    id: str
    customer_id: int
    good_id: int = 0
    phone: str
    address: str
    appointment_time: str
    total_fee: int
    quantity: int = 1
    status: int
    create_time: int
    good_title: str = ""
    good_img_url: str = ""
    good_duration: int = 0
    customer_nickname: str = ""

    class Config:
        from_attributes = True


class MerchantContactOut(BaseModel):
    id: int
    name: str
    wechat: str
    phone: str
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


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
    merchant_contact_name: str = ""
    message_type: str
    content: str
    order_id: str = ""
    payload: dict | None = None
    create_time: int


class ConversationReadIn(BaseModel):
    last_message_id: int


class ConversationDefaultContactIn(BaseModel):
    merchant_contact_id: int


# ---- Chat ----
class ChatMessage(BaseModel):
    thread_type: str     # "order" / "consultation"
    thread_id: str
    content: str


class ChatLogOut(BaseModel):
    id: int
    thread_type: str
    thread_id: str
    sender_id: int
    sender_role: str
    content: str
    create_time: int

    class Config:
        from_attributes = True


# ---- User ----
class UserOut(BaseModel):
    id: int
    openid: str
    nickname: str
    role: str
    phone: str

    class Config:
        from_attributes = True


class AdminLogin(BaseModel):
    password: str


class UserCreate(BaseModel):
    openid: str
    role: str = "CUSTOMER"
    nickname: str = ""
    phone: str = ""


class UserUpdate(BaseModel):
    role: Optional[str] = None
    nickname: Optional[str] = None
    phone: Optional[str] = None
