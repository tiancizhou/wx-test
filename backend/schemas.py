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


# ---- Order ----
class ConsultCreate(BaseModel):
    good_id: int


class OrderCreate(BaseModel):
    good_id: int
    phone: str
    address: str
    appointment_time: str
    quantity: int = 1


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
