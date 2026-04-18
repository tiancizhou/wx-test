import time
import uuid
from enum import IntEnum

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, DateTime, Enum as SAEnum, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Role(str):
    CUSTOMER = "CUSTOMER"
    MERCHANT = "MERCHANT"


class OrderStatus(IntEnum):
    UNPAID = 0          # 待付款
    ORDERED = 1         # 已下单
    COMPLETED = 2       # 已完成
    REFUNDING = 3       # 退款中
    REFUNDED = 4        # 已退款


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    openid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default=Role.CUSTOMER)
    phone: Mapped[str] = mapped_column(String(20), default="")

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Good(Base):
    __tablename__ = "goods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[int] = mapped_column(Integer, comment="价格，单位分")
    original_price: Mapped[int] = mapped_column(Integer, default=0, comment="原价，单位分")
    duration: Mapped[int] = mapped_column(Integer, default=60, comment="时长，单位分钟")
    img_url: Mapped[str] = mapped_column(String(512), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sales: Mapped[int] = mapped_column(Integer, default=0, comment="销量")
    detail_images: Mapped[str] = mapped_column(Text, default="[]", comment="详情图JSON数组")


def _generate_order_id():
    """生成订单号: 时间戳 + 6位随机数"""
    return f"{int(time.time())}{uuid.uuid4().hex[:6].upper()}"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_generate_order_id)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    good_id: Mapped[int] = mapped_column(ForeignKey("goods.id"), default=0)
    phone: Mapped[str] = mapped_column(String(20), default="")
    address: Mapped[str] = mapped_column(String(256), default="")
    appointment_time: Mapped[str] = mapped_column(String(32), default="")
    total_fee: Mapped[int] = mapped_column(Integer, default=0, comment="金额，单位分")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="商品数量")
    transaction_id: Mapped[str] = mapped_column(String(32), default="", comment="微信支付订单号")
    refund_id: Mapped[str] = mapped_column(String(32), default="", comment="微信退款单号")
    status: Mapped[int] = mapped_column(Integer, default=OrderStatus.UNPAID)
    create_time: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

    customer: Mapped["User"] = relationship(back_populates="orders")
    good: Mapped["Good"] = relationship()


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
    default_merchant_contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchant_contacts.id"),
        nullable=True,
    )
    create_time: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

    customer: Mapped["User"] = relationship()
    default_merchant_contact: Mapped["MerchantContact | None"] = relationship()


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

    merchant_contact: Mapped["MerchantContact | None"] = relationship()


class ConversationReadState(Base):
    __tablename__ = "conversation_read_states"
    __table_args__ = (PrimaryKeyConstraint("user_id", "conversation_id", "reader_role"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    reader_role: Mapped[str] = mapped_column(String(16), default="")
    last_read_message_id: Mapped[int] = mapped_column(Integer, default=0)


class Consultation(Base):
    __tablename__ = "consultations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    good_id: Mapped[int] = mapped_column(ForeignKey("goods.id"))
    create_time: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

    customer: Mapped["User"] = relationship()
    good: Mapped["Good"] = relationship()


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    thread_type: Mapped[str] = mapped_column(String(16))   # "order" / "consultation"
    thread_id: Mapped[str] = mapped_column(String(32), index=True)
    sender_id: Mapped[int] = mapped_column(Integer)
    sender_role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    create_time: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))


class ChatReadState(Base):
    __tablename__ = "chat_read_states_v3"
    __table_args__ = (PrimaryKeyConstraint("user_id", "thread_id", "reader_role"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    thread_type: Mapped[str] = mapped_column(String(16))
    thread_id: Mapped[str] = mapped_column(String(32))
    reader_role: Mapped[str] = mapped_column(String(16), default="")
    last_read_id: Mapped[int] = mapped_column(Integer, default=0)
