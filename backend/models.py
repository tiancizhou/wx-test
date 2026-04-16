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
    CONSULTATION = -1   # 咨询（未下单）
    UNPAID = 0          # 待付款
    ORDERED = 1         # 已下单
    COMPLETED = 2       # 已完成
    REFUNDED = 3        # 已退款


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
    chat_logs: Mapped[list["ChatLog"]] = relationship(back_populates="order", order_by="ChatLog.create_time")


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    sender_id: Mapped[int] = mapped_column(Integer)
    sender_role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    create_time: Mapped[int] = mapped_column(Integer, default=lambda: int(time.time()))

    order: Mapped["Order"] = relationship(back_populates="chat_logs")


class ChatReadState(Base):
    __tablename__ = "chat_read_states_v2"
    __table_args__ = (PrimaryKeyConstraint("user_id", "order_id", "reader_role"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    reader_role: Mapped[str] = mapped_column(String(16), default="")
    last_read_id: Mapped[int] = mapped_column(Integer, default=0)
