from pydantic import BaseModel
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


class GoodCreate(BaseModel):
    title: str
    description: str = ""
    price: int
    original_price: int = 0
    duration: int = 60
    img_url: str = ""


# ---- Order ----
class OrderCreate(BaseModel):
    good_id: int
    phone: str
    address: str
    appointment_time: str


class OrderOut(BaseModel):
    id: str
    customer_id: int
    phone: str
    address: str
    appointment_time: str
    total_fee: int
    status: int
    create_time: int

    class Config:
        from_attributes = True


# ---- Chat ----
class ChatMessage(BaseModel):
    order_id: str
    content: str


class ChatLogOut(BaseModel):
    id: int
    order_id: str
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
