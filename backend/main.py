import time
import hashlib
import xml.etree.cElementTree as ET
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, init_db
from models import User, Good, Order, OrderStatus, ChatLog, Role
from schemas import GoodOut, GoodUpdate, OrderCreate, OrderOut, ChatMessage, ChatLogOut, UserOut
from deps import get_current_user, require_role
from wechat.config import settings
from wechat.token import get_jssdk_signature
from wechat.menu import create_menu as wx_create_menu
from wechat.template import notify_order_accepted, notify_order_completed


# ---- Lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="到家按摩预约系统", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 微信消息推送
# ============================================================

def check_signature(signature: str, timestamp: str, nonce: str) -> bool:
    params = [settings.TOKEN, timestamp, nonce]
    params.sort()
    hash_str = hashlib.sha1("".join(params).encode("utf-8")).hexdigest()
    return hash_str == signature


@app.get("/wechat")
async def wechat_verify(signature: str, timestamp: str, nonce: str, echostr: str):
    """微信服务器 URL 验证"""
    if check_signature(signature, timestamp, nonce):
        return Response(content=echostr, media_type="text/plain")
    return Response(content="Invalid signature", status_code=403)


@app.post("/wechat")
async def wechat_message(request: Request, db: AsyncSession = Depends(get_db)):
    """接收微信消息与事件推送"""
    body = (await request.body()).decode("utf-8")
    msg_signature = request.query_params.get("msg_signature", "")
    timestamp = request.query_params.get("timestamp", "")
    nonce = request.query_params.get("nonce", "")

    if msg_signature:
        from wechat.crypto import WXBizMsgCrypt
        crypto = WXBizMsgCrypt(settings.TOKEN, settings.ENCODING_AES_KEY, settings.APP_ID)
        ret, xml_content = crypto.DecryptMsg(body, msg_signature, timestamp, nonce)
        if ret != 0:
            return Response(content=f"Decrypt error: {ret}", status_code=400)
    else:
        xml_content = body

    root = ET.fromstring(xml_content)
    msg_type = root.findtext("MsgType", "")
    from_user = root.findtext("FromUserName", "")
    to_user = root.findtext("ToUserName", "")

    if msg_type == "event":
        event = root.findtext("Event", "")
        if event in ("subscribe", "SCAN"):
            # 关注/扫码：自动创建用户 + 返回欢迎语
            result = await db.execute(select(User).where(User.openid == from_user))
            user = result.scalar_one_or_none()
            if not user:
                user = User(openid=from_user, role=Role.CUSTOMER)
                db.add(user)
                await db.commit()

            reply = f"""<xml>
<ToUserName><![CDATA[{from_user}]]></ToUserName>
<FromUserName><![CDATA[{to_user}]]></FromUserName>
<CreateTime>{int(time.time())}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[欢迎关注！点击下方菜单开始预约按摩服务。]]></Content>
</xml>"""
            return Response(content=reply, media_type="application/xml")

    return Response(content="success", media_type="text/plain")


# ============================================================
# 商品
# ============================================================

@app.get("/goods", response_model=list[GoodOut])
async def list_goods(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Good).where(Good.is_active == True))
    return result.scalars().all()


@app.put("/goods/{good_id}", response_model=GoodOut)
async def update_good(
    good_id: int,
    data: GoodUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT, Role.ADMIN)),
):
    result = await db.execute(select(Good).where(Good.id == good_id))
    good = result.scalar_one_or_none()
    if not good:
        raise HTTPException(404, "商品不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(good, k, v)
    await db.commit()
    await db.refresh(good)
    return good


# ============================================================
# 订单
# ============================================================

@app.post("/orders", response_model=OrderOut)
async def create_order(
    data: OrderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Good).where(Good.id == data.good_id, Good.is_active == True))
    good = result.scalar_one_or_none()
    if not good:
        raise HTTPException(404, "商品不存在")

    order = Order(
        customer_id=user.id,
        phone=data.phone,
        address=data.address,
        appointment_time=data.appointment_time,
        total_fee=good.price,
        status=OrderStatus.PENDING,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@app.get("/my_orders", response_model=list[OrderOut])
async def my_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Order).where(Order.customer_id == user.id).order_by(Order.create_time.desc())
    )
    return result.scalars().all()


@app.get("/orders/pending", response_model=list[OrderOut])
async def pending_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT, Role.SERVICE, Role.ADMIN)),
):
    result = await db.execute(
        select(Order).where(Order.status == OrderStatus.PENDING).order_by(Order.create_time.desc())
    )
    return result.scalars().all()


@app.get("/orders/active", response_model=list[OrderOut])
async def active_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT, Role.SERVICE, Role.ADMIN)),
):
    result = await db.execute(
        select(Order).where(Order.status.in_([OrderStatus.PENDING, OrderStatus.ACCEPTED]))
        .order_by(Order.create_time.desc())
    )
    return result.scalars().all()


@app.post("/orders/{order_id}/accept")
async def accept_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT, Role.ADMIN)),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != OrderStatus.PENDING:
        raise HTTPException(400, "订单状态不允许接单")
    order.status = OrderStatus.ACCEPTED
    await db.commit()

    # 推送模板消息通知客户
    try:
        await db.refresh(order.customer)
        await notify_order_accepted(
            openid=order.customer.openid,
            order_id=order.id,
            appointment_time=order.appointment_time,
        )
    except Exception as e:
        print(f"[WARN] 模板消息推送失败: {e}")

    return {"msg": "接单成功"}


@app.post("/orders/{order_id}/complete")
async def complete_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT, Role.ADMIN)),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != OrderStatus.ACCEPTED:
        raise HTTPException(400, "订单状态不允许完成")
    order.status = OrderStatus.COMPLETED
    await db.commit()

    # 推送模板消息通知客户
    try:
        await db.refresh(order.customer)
        await notify_order_completed(
            openid=order.customer.openid,
            order_id=order.id,
        )
    except Exception as e:
        print(f"[WARN] 模板消息推送失败: {e}")

    return {"msg": "订单已完成"}


# ============================================================
# 聊天
# ============================================================

@app.get("/chat/{order_id}", response_model=list[ChatLogOut])
async def get_chat(
    order_id: str,
    after_id: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatLog)
        .where(ChatLog.order_id == order_id, ChatLog.id > after_id)
        .order_by(ChatLog.create_time)
    )
    return result.scalars().all()


@app.post("/chat", response_model=ChatLogOut)
async def send_chat(
    data: ChatMessage,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    log = ChatLog(
        order_id=data.order_id,
        sender_id=user.id,
        sender_role=user.role,
        content=data.content,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


# ============================================================
# 用户信息
# ============================================================

@app.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return user


# ============================================================
# 微信网页授权
# ============================================================

@app.get("/wechat/auth")
async def wechat_auth(code: str, db: AsyncSession = Depends(get_db)):
    """微信网页授权回调，用 code 换取 openid 并登录/注册"""
    import httpx
    url = "https://api.weixin.qq.com/sns/oauth2/access_token"
    params = {
        "appid": settings.APP_ID,
        "secret": settings.APP_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        data = resp.json()

    openid = data.get("openid")
    if not openid:
        raise HTTPException(400, "微信授权失败")

    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(openid=openid, role=Role.CUSTOMER)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return {"token": openid, "user": UserOut.model_validate(user)}


# ============================================================
# JS-SDK 签名
# ============================================================

@app.get("/wechat/jssdk")
async def jssdk_config(url: str):
    """返回 JS-SDK 页面签名配置"""
    try:
        return await get_jssdk_signature(url)
    except Exception as e:
        raise HTTPException(500, f"JS-SDK 签名失败: {e}")


# ============================================================
# 自定义菜单
# ============================================================

@app.post("/wechat/menu")
async def setup_menu(
    base_url: str,
    user: User = Depends(require_role(Role.ADMIN)),
):
    """管理员创建自定义菜单"""
    result = await wx_create_menu(base_url)
    if result.get("errcode", 0) != 0:
        raise HTTPException(400, f"菜单创建失败: {result}")
    return {"msg": "菜单创建成功", "data": result}


# ============================================================
# 前端页面
# ============================================================

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/customer")
async def customer_page():
    return FileResponse(FRONTEND_DIR / "customer.html")


@app.get("/merchant")
async def merchant_page():
    return FileResponse(FRONTEND_DIR / "merchant.html")


@app.get("/service")
async def service_page():
    return FileResponse(FRONTEND_DIR / "service.html")


# ============================================================
# 静态文件（微信域名验证等）
# ============================================================

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# 微信域名验证文件（根路径）
@app.get("/MP_verify_{file_id}.txt")
async def mp_verify(file_id: str):
    f = STATIC_DIR / f"MP_verify_{file_id}.txt"
    if f.exists():
        return FileResponse(f, media_type="text/plain")
    raise HTTPException(404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
