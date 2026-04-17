import time
import hashlib
import json
import uuid
import asyncio
import xml.etree.cElementTree as ET
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request, Response, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import case, select, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, init_db
from models import User, Good, Order, OrderStatus, Consultation, ChatLog, ChatReadState, Role
from schemas import GoodOut, GoodUpdate, GoodCreate, ConsultCreate, ConsultationOut, OrderOut, ChatMessage, ChatLogOut, UserOut, AdminLogin, UserCreate, UserUpdate
from deps import get_current_user, require_role


def _order_to_out(order: Order) -> dict:
    """将 Order ORM 对象转为带商品和客户信息的字典"""
    good = order.good
    customer = order.customer
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "good_id": order.good_id,
        "phone": order.phone,
        "address": order.address,
        "appointment_time": order.appointment_time,
        "total_fee": order.total_fee,
        "quantity": order.quantity,
        "status": order.status,
        "create_time": order.create_time,
        "good_title": good.title if good else "",
        "good_img_url": good.img_url if good else "",
        "good_duration": good.duration if good else 0,
        "customer_nickname": customer.nickname if customer else "",
    }
from wechat.config import settings
from wechat.token import get_jssdk_signature
from wechat.menu import create_menu as wx_create_menu
from wechat.template import notify_order_completed


# ---- Lifespan ----

STALE_ORDER_CLEANUP_INTERVAL = 600  # 每 10 分钟清理一次
STALE_ORDER_MAX_AGE = 1800  # 超过 30 分钟未支付视为过期


async def _cleanup_stale_unpaid_orders():
    """后台任务：定期清理过期未支付订单"""
    while True:
        await asyncio.sleep(STALE_ORDER_CLEANUP_INTERVAL)
        try:
            from database import async_session
            cutoff = int(time.time()) - STALE_ORDER_MAX_AGE
            async with async_session() as db:
                result = await db.execute(
                    select(Order).where(
                        Order.status == OrderStatus.UNPAID,
                        Order.create_time < cutoff,
                    )
                )
                stale_orders = result.scalars().all()
                for order in stale_orders:
                    if not settings.PAY_MOCK:
                        try:
                            await close_order(order.id)
                        except Exception:
                            pass
                    await db.delete(order)
                if stale_orders:
                    await db.commit()
                    print(f"[CLEANUP] 清理 {len(stale_orders)} 个过期未支付订单")
        except Exception as e:
            print(f"[CLEANUP] 清理失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_payment_config(require_platform_public_key=True)
    await init_db()
    task = asyncio.create_task(_cleanup_stale_unpaid_orders())
    yield
    task.cancel()

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

        elif event == "user_authorization_revoke":
            # 用户撤回授权：清理用户敏感信息
            result = await db.execute(select(User).where(User.openid == from_user))
            user = result.scalar_one_or_none()
            if user:
                user.nickname = None
                user.phone = None
                await db.commit()

        elif event == "user_authorization_cancellation":
            # 用户注销：删除用户数据
            result = await db.execute(select(User).where(User.openid == from_user))
            user = result.scalar_one_or_none()
            if user:
                await db.delete(user)
                await db.commit()

        elif event == "user_info_modified":
            # 用户资料变更：清除缓存的昵称等信息
            result = await db.execute(select(User).where(User.openid == from_user))
            user = result.scalar_one_or_none()
            if user:
                user.nickname = None
                await db.commit()

    return Response(content="success", media_type="text/plain")


# ============================================================
# 商品
# ============================================================

@app.get("/goods", response_model=list[GoodOut])
async def list_goods(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Good).where(Good.is_active == True))
    return result.scalars().all()


@app.get("/goods/all", response_model=list[GoodOut])
async def list_all_goods(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    """商家：获取全部商品（含已下架）"""
    result = await db.execute(select(Good).order_by(Good.id))
    return result.scalars().all()


@app.get("/goods/{good_id}", response_model=GoodOut)
async def get_good(good_id: int, db: AsyncSession = Depends(get_db)):
    """获取单个商品详情（含已下架）"""
    good = await db.get(Good, good_id)
    if not good:
        raise HTTPException(404, "商品不存在")
    return good


@app.post("/goods", response_model=GoodOut)
async def create_good(
    data: GoodCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    """创建商品"""
    good = Good(**data.model_dump())
    db.add(good)
    await db.commit()
    await db.refresh(good)
    return good


@app.put("/goods/{good_id}", response_model=GoodOut)
async def update_good(
    good_id: int,
    data: GoodUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
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


@app.delete("/goods/{good_id}")
async def delete_good(
    good_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    """删除商品"""
    result = await db.execute(select(Good).where(Good.id == good_id))
    good = result.scalar_one_or_none()
    if not good:
        raise HTTPException(404, "商品不存在")
    await db.delete(good)
    await db.commit()
    return {"msg": "已删除"}


# ============================================================
# 图片上传
# ============================================================

UPLOAD_DIR = Path(__file__).parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    """上传图片，返回可访问的 URL"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "只能上传图片文件")
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4().hex[:12]}.{ext}"
    filepath = UPLOAD_DIR / filename
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过5MB")
    with open(filepath, "wb") as f:
        f.write(content)
    return {"url": f"/static/uploads/{filename}"}


# ============================================================
# 会话访问权限校验
# ============================================================

async def _verify_thread_access(thread_type: str, thread_id: str, user: User, db: AsyncSession):
    """校验会话存在性及当前用户是否有权访问。商家可访问所有，客户只能访问自己的。"""
    if thread_type == "order":
        result = await db.execute(
            select(Order).where(Order.id == thread_id).options(selectinload(Order.good))
        )
        obj = result.scalar_one_or_none()
    elif thread_type == "consultation":
        result = await db.execute(
            select(Consultation).where(Consultation.id == int(thread_id)).options(selectinload(Consultation.good))
        )
        obj = result.scalar_one_or_none()
    else:
        raise HTTPException(400, "无效的会话类型")
    if not obj:
        raise HTTPException(404, "会话不存在")
    if user.role == Role.MERCHANT:
        return obj
    if obj.customer_id != user.id:
        raise HTTPException(403, "无权访问该会话")
    return obj


async def _verify_order_access(order_id: str, user: User, db: AsyncSession) -> Order:
    """校验订单存在性及当前用户是否有权访问。商家可访问所有订单，客户只能访问自己的。"""
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.good))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")
    if user.role == Role.MERCHANT:
        return order
    if order.customer_id != user.id:
        raise HTTPException(403, "无权访问该订单")
    return order


# ============================================================
# 支付
# ============================================================

from wechat.pay import create_prepay_order, generate_jsapi_params, verify_pay_notify, query_order, create_refund, verify_refund_notify, close_order


async def _load_order_for_payment_update(order_id: str, db: AsyncSession) -> Order:
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.good))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise LookupError("订单不存在")
    return order


async def apply_payment_success(
    order_id: str,
    db: AsyncSession,
    transaction_id: str = "",
    amount_total: int | None = None,
    appid: str = "",
    mchid: str = "",
):
    order = await _load_order_for_payment_update(order_id, db)
    if amount_total is not None and amount_total != order.total_fee:
        raise ValueError("支付回调金额不匹配")
    if appid and appid != settings.APP_ID:
        raise ValueError("支付回调 appid 不匹配")
    if mchid and mchid != settings.MCH_ID:
        raise ValueError("支付回调 mchid 不匹配")

    qty = order.quantity or 1

    payment_update = await db.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == OrderStatus.UNPAID)
        .values(
            status=OrderStatus.ORDERED,
            transaction_id=transaction_id if transaction_id else Order.transaction_id,
        )
        .execution_options(synchronize_session=False)
    )
    if payment_update.rowcount == 0:
        await db.rollback()
        return False

    await db.execute(
        update(Good)
        .where(Good.id == order.good_id)
        .values(sales=Good.sales + qty)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return True


async def apply_refund_success(
    order_id: str,
    db: AsyncSession,
    refund_id: str = "",
):
    order = await _load_order_for_payment_update(order_id, db)
    if order.status == OrderStatus.REFUNDED:
        return False
    if order.status not in (OrderStatus.ORDERED, OrderStatus.COMPLETED, OrderStatus.REFUNDING):
        raise ValueError("订单状态不支持退款成功")

    qty = order.quantity or 1
    refund_update = await db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.status.in_((OrderStatus.ORDERED, OrderStatus.COMPLETED, OrderStatus.REFUNDING)),
        )
        .values(
            status=OrderStatus.REFUNDED,
            refund_id=refund_id if refund_id else Order.refund_id,
        )
        .execution_options(synchronize_session=False)
    )
    if refund_update.rowcount == 0:
        await db.rollback()
        return False

    await db.execute(
        update(Good)
        .where(Good.id == order.good_id)
        .values(
            sales=case(
                (Good.sales > qty, Good.sales - qty),
                else_=0,
            )
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return True


@app.post("/pay/create")
async def pay_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建预支付订单：先创建 UNPAID 订单，再发起支付"""
    body = await request.json()
    good_id = body.get("good_id")
    phone = body.get("phone", "")
    address = body.get("address", "")
    appointment_time = body.get("appointment_time", "")
    qty = body.get("quantity", 1) or 1

    result = await db.execute(select(Good).where(Good.id == good_id, Good.is_active == True))
    good = result.scalar_one_or_none()
    if not good:
        raise HTTPException(404, "商品不存在")

    total_fee = good.price * qty

    # 创建 UNPAID 订单
    order = Order(
        customer_id=user.id,
        good_id=good.id,
        phone=phone,
        address=address,
        appointment_time=appointment_time,
        quantity=qty,
        total_fee=total_fee,
        status=OrderStatus.UNPAID,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    # Mock 模式：保留未支付状态，等待显式确认
    if settings.PAY_MOCK:
        return {"mock": True, "order_id": order.id, "status": "NOTPAY"}

    # 真实模式：调微信统一下单
    try:
        notify_url = str(request.base_url).rstrip("/") + "/pay/notify"
        client_ip = request.client.host if request.client else "127.0.0.1"
        prepay_id = await create_prepay_order(
            order_id=order.id,
            openid=user.openid,
            total_fee=total_fee,
            description=good.title[:127],
            notify_url=notify_url,
            client_ip=client_ip,
        )
        pay_params = generate_jsapi_params(prepay_id)
        return {"mock": False, "order_id": order.id, "pay_params": pay_params}
    except Exception as e:
        # 下单失败，删除 UNPAID 订单
        await db.delete(order)
        await db.commit()
        raise HTTPException(500, f"支付下单失败: {e}")


@app.post("/pay/notify")
async def pay_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """微信支付 V3 支付成功回调通知"""
    body = (await request.body()).decode("utf-8")
    timestamp = request.headers.get("Wechatpay-Timestamp", "")
    nonce = request.headers.get("Wechatpay-Nonce", "")
    signature = request.headers.get("Wechatpay-Signature", "")
    wechatpay_serial = request.headers.get("Wechatpay-Serial", "")

    data = verify_pay_notify(timestamp, nonce, body, signature, wechatpay_serial=wechatpay_serial)
    if not data:
        return JSONResponse({"code": "FAIL", "message": "验签或解密失败"}, status_code=400)

    if data.get("event_type") != "TRANSACTION.SUCCESS":
        return Response(status_code=200)

    resource = data.get("resource", {})
    if resource.get("trade_state") != "SUCCESS":
        return Response(status_code=200)

    order_id = resource.get("out_trade_no", "")
    if not order_id:
        return JSONResponse({"code": "FAIL", "message": "缺少订单号"}, status_code=400)

    result = await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.good))
    )
    order = result.scalar_one_or_none()
    if not order:
        return JSONResponse({"code": "FAIL", "message": "订单不存在"}, status_code=404)

    await apply_payment_success(
        order.id,
        db,
        transaction_id=resource.get("transaction_id", ""),
        amount_total=resource.get("amount", {}).get("total"),
        appid=resource.get("appid", ""),
        mchid=resource.get("mchid", ""),
    )

    return Response(status_code=200)


@app.post("/pay/mock/confirm/{order_id}")
async def pay_mock_confirm(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not settings.PAY_MOCK:
        raise HTTPException(404, "仅 mock 模式可用")

    order = await _verify_order_access(order_id, user, db)
    if order.status != OrderStatus.UNPAID:
        raise HTTPException(400, "订单状态不允许确认支付")

    await apply_payment_success(order.id, db, transaction_id=f"mock-{order.id}")
    return {"mock": True, "order_id": order.id, "status": "SUCCESS"}


@app.post("/pay/query/{order_id}")
async def pay_query(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询订单支付状态（调微信 V3 查单 API）"""
    order = await _verify_order_access(order_id, user, db)
    if settings.PAY_MOCK:
        trade_state = "SUCCESS" if order.status != OrderStatus.UNPAID else "NOTPAY"
        return {"mock": True, "trade_state": trade_state}
    try:
        result = await query_order(order_id)
        return {"mock": False, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/pay/close/{order_id}")
async def pay_close(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """关闭未支付订单：调微信关单 API 并删除 UNPAID 订单"""
    order = await _verify_order_access(order_id, user, db)
    if order.status != OrderStatus.UNPAID:
        raise HTTPException(400, "订单状态不允许关闭")

    if not settings.PAY_MOCK:
        try:
            await close_order(order_id)
        except Exception as e:
            print(f"[WARN] 微信关单失败 (订单可能已过期): {e}")

    await db.delete(order)
    await db.commit()
    return {"msg": "已关闭"}


@app.post("/pay/refund/{order_id}")
async def pay_refund(
    order_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """申请退款"""
    order = await _verify_order_access(order_id, user, db)
    if order.status not in (OrderStatus.ORDERED, OrderStatus.COMPLETED):
        raise HTTPException(400, "订单状态不支持退款")

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    refund_amount = body.get("refund_amount", order.total_fee)
    reason = body.get("reason", "商户退款")

    if settings.PAY_MOCK:
        await apply_refund_success(order.id, db, refund_id=f"mock-refund-{order.id}")
        return {"mock": True, "status": "SUCCESS"}

    out_refund_no = f"R{order_id}"
    notify_url = str(request.base_url).rstrip("/") + "/refund/notify"
    try:
        resp = await create_refund(
            out_trade_no=order.id,
            out_refund_no=out_refund_no,
            total=order.total_fee,
            refund=refund_amount,
            notify_url=notify_url,
            reason=reason,
            transaction_id=order.transaction_id,
        )
        order.status = OrderStatus.REFUNDING
        order.refund_id = resp.get("refund_id", "")
        await db.commit()
        return {"mock": False, "status": resp.get("status", "PROCESSING"), "refund_id": resp.get("refund_id")}
    except Exception as e:
        raise HTTPException(500, f"退款申请失败: {e}")


@app.post("/refund/notify")
async def refund_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """退款结果回调通知"""
    body = (await request.body()).decode("utf-8")
    timestamp = request.headers.get("Wechatpay-Timestamp", "")
    nonce = request.headers.get("Wechatpay-Nonce", "")
    signature = request.headers.get("Wechatpay-Signature", "")
    wechatpay_serial = request.headers.get("Wechatpay-Serial", "")

    data = verify_refund_notify(timestamp, nonce, body, signature, wechatpay_serial=wechatpay_serial)
    if not data:
        return JSONResponse({"code": "FAIL", "message": "验签或解密失败"}, status_code=400)

    resource = data.get("resource", {})
    refund_status = resource.get("refund_status", "")

    if refund_status == "SUCCESS":
        order_id = resource.get("out_trade_no", "")
        if not order_id:
            return JSONResponse({"code": "FAIL", "message": "缺少订单号"}, status_code=400)

        result = await db.execute(
            select(Order).where(Order.id == order_id).options(selectinload(Order.good))
        )
        order = result.scalar_one_or_none()
        if order:
            await apply_refund_success(
                order.id,
                db,
                refund_id=resource.get("refund_id", order.refund_id),
            )

    return Response(status_code=200)


@app.get("/my_orders", response_model=list[OrderOut])
async def my_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Order).options(selectinload(Order.good))
        .where(Order.customer_id == user.id).order_by(Order.create_time.desc())
    )
    return [_order_to_out(o) for o in result.scalars().all()]


@app.get("/orders/pending", response_model=list[OrderOut])
async def pending_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    result = await db.execute(
        select(Order).options(selectinload(Order.good))
        .where(Order.status == OrderStatus.ORDERED).order_by(Order.create_time.desc())
    )
    return [_order_to_out(o) for o in result.scalars().all()]


@app.post("/consult")
async def create_consult(
    data: ConsultCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """客户：发起或获取商品咨询会话（同一用户+商品只建一个）"""
    existing = await db.execute(
        select(Consultation).options(selectinload(Consultation.good))
        .where(
            Consultation.customer_id == user.id,
            Consultation.good_id == data.good_id,
        )
    )
    consult = existing.scalar_one_or_none()
    if consult:
        return {
            "thread_type": "consultation",
            "thread_id": str(consult.id),
            "good_id": consult.good_id,
            "good_title": consult.good.title if consult.good else "",
            "good_img_url": consult.good.img_url if consult.good else "",
            "create_time": consult.create_time,
        }

    consult = Consultation(customer_id=user.id, good_id=data.good_id)
    db.add(consult)
    await db.commit()
    await db.refresh(consult)
    result = await db.execute(
        select(Consultation).options(selectinload(Consultation.good)).where(Consultation.id == consult.id)
    )
    consult = result.scalar_one()
    return {
        "thread_type": "consultation",
        "thread_id": str(consult.id),
        "good_id": consult.good_id,
        "good_title": consult.good.title if consult.good else "",
        "good_img_url": consult.good.img_url if consult.good else "",
        "create_time": consult.create_time,
    }


@app.get("/orders/active")
async def active_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    # --- 订单 ---
    order_result = await db.execute(
        select(Order).options(selectinload(Order.good), selectinload(Order.customer))
        .order_by(Order.create_time.desc())
    )
    all_orders = order_result.scalars().all()

    # --- 咨询 ---
    consult_result = await db.execute(
        select(Consultation).options(selectinload(Consultation.good), selectinload(Consultation.customer))
        .order_by(Consultation.create_time.desc())
    )
    all_consults = consult_result.scalars().all()

    if not all_orders and not all_consults:
        return []

    # 收集所有 thread_id
    order_thread_ids = [o.id for o in all_orders]
    consult_thread_ids = [str(c.id) for c in all_consults]
    all_thread_ids = order_thread_ids + consult_thread_ids

    # 批量查询最后一条消息
    last_msg_rows = await db.execute(
        select(
            ChatLog.thread_type,
            ChatLog.thread_id,
            ChatLog.id,
            ChatLog.create_time,
            ChatLog.sender_role,
            ChatLog.content,
        ).where(
            ChatLog.id.in_(
                select(func.max(ChatLog.id)).where(ChatLog.thread_id.in_(all_thread_ids)).group_by(ChatLog.thread_id)
            )
        )
    )
    last_msg_map = {}
    for row in last_msg_rows.all():
        key = f"{row[0]}:{row[1]}"
        last_msg_map[key] = {
            "id": row[2], "create_time": row[3],
            "sender_role": row[4], "content": row[5][:50] if row[5] else "",
        }

    # 批量查询已读状态
    read_rows = await db.execute(
        select(ChatReadState).where(
            ChatReadState.user_id == user.id,
            ChatReadState.thread_id.in_(all_thread_ids),
            ChatReadState.reader_role == user.role,
        )
    )
    read_map = {f"{r.thread_type}:{r.thread_id}": r.last_read_id for r in read_rows.scalars().all()}

    # 批量查询全部未读消息数
    unread_rows = await db.execute(
        select(ChatLog.thread_type, ChatLog.thread_id, func.count(ChatLog.id)).where(
            ChatLog.thread_id.in_(all_thread_ids),
            ChatLog.sender_role != user.role,
        ).group_by(ChatLog.thread_type, ChatLog.thread_id)
    )
    all_unread = {}
    for ttype, tid, cnt in unread_rows.all():
        all_unread[f"{ttype}:{tid}"] = cnt

    # 对有 read_state 的精确计算
    unread_map = {}
    for key, last_read_id in read_map.items():
        ttype, tid = key.split(":", 1)
        cnt = await db.scalar(
            select(func.count()).select_from(ChatLog).where(
                ChatLog.thread_type == ttype,
                ChatLog.thread_id == tid,
                ChatLog.id > last_read_id,
                ChatLog.sender_role != user.role,
            )
        )
        unread_map[key] = cnt

    for key in [f"order:{tid}" for tid in order_thread_ids] + [f"consultation:{tid}" for tid in consult_thread_ids]:
        if key not in unread_map:
            unread_map[key] = all_unread.get(key, 0)

    # 组装结果
    items = []

    for o in all_orders:
        out = _order_to_out(o)
        out["thread_type"] = "order"
        out["thread_id"] = o.id
        key = f"order:{o.id}"
        msg = last_msg_map.get(key)
        out["last_msg_id"] = msg["id"] if msg else 0
        out["last_msg_time"] = msg["create_time"] if msg else 0
        out["last_sender_role"] = msg["sender_role"] if msg else ""
        out["last_content"] = msg["content"] if msg else ""
        out["unread_count"] = unread_map.get(key, 0)
        items.append(out)

    for c in all_consults:
        key = f"consultation:{c.id}"
        msg = last_msg_map.get(key)
        items.append({
            "thread_type": "consultation",
            "thread_id": str(c.id),
            "id": f"C{c.id}",
            "customer_id": c.customer_id,
            "customer_nickname": c.customer.nickname if c.customer else "",
            "good_id": c.good_id,
            "good_title": c.good.title if c.good else "",
            "good_img_url": c.good.img_url if c.good else "",
            "good_duration": c.good.duration if c.good else 0,
            "phone": "", "address": "", "appointment_time": "",
            "total_fee": 0, "quantity": 1,
            "status": -1,  # consultation marker for frontend compatibility
            "create_time": c.create_time,
            "last_msg_id": msg["id"] if msg else 0,
            "last_msg_time": msg["create_time"] if msg else 0,
            "last_sender_role": msg["sender_role"] if msg else "",
            "last_content": msg["content"] if msg else "",
            "unread_count": unread_map.get(key, 0),
        })

    # 按最后消息时间倒序，没有消息的按创建时间
    items.sort(key=lambda x: x.get("last_msg_time") or x.get("create_time", 0), reverse=True)
    return items


@app.post("/orders/{order_id}/complete")
async def complete_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.customer))
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")
    if order.status != OrderStatus.ORDERED:
        raise HTTPException(400, "订单状态不允许完成")
    order.status = OrderStatus.COMPLETED
    await db.commit()

    # 推送模板消息通知客户
    try:
        await notify_order_completed(
            openid=order.customer.openid,
            order_id=order.id,
        )
    except Exception as e:
        print(f"[WARN] 模板消息推送失败: {e}")

    return {"msg": "订单已完成"}


# ============================================================
# 统计
# ============================================================

import datetime
from sqlalchemy import distinct


def _day_start_ts(dt=None):
    """获取某天 0 点的 unix 时间戳"""
    if dt is None:
        dt = datetime.date.today()
    return int(datetime.datetime.combine(dt, datetime.time.min).timestamp())


@app.get("/stats/dashboard")
async def stats_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(Role.MERCHANT)),
):
    """商家端统计数据：今日/本月营收、订单数、客户数、状态分布、商品排行"""
    today_start = _day_start_ts()
    now = datetime.date.today()
    month_start = _day_start_ts(datetime.date(now.year, now.month, 1))

    # 有效订单状态（排除未支付）
    valid_status = [OrderStatus.ORDERED, OrderStatus.COMPLETED, OrderStatus.REFUNDING, OrderStatus.REFUNDED]
    paid_status = [OrderStatus.ORDERED, OrderStatus.COMPLETED]

    async def _period_stats(start_ts):
        base = select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_fee), 0),
            func.count(distinct(Order.customer_id)),
        ).where(Order.status.in_(valid_status), Order.create_time >= start_ts)
        result = await db.execute(base)
        row = result.one()
        count, revenue, customers = row
        avg = revenue // count if count > 0 else 0
        return {"order_count": count, "revenue": revenue, "customers": customers, "avg_fee": avg}

    today = await _period_stats(today_start)
    month = await _period_stats(month_start)

    # 状态分布（本月）
    status_result = await db.execute(
        select(Order.status, func.count(Order.id))
        .where(Order.create_time >= month_start)
        .group_by(Order.status)
    )
    status_names = {1: "ordered", 2: "completed", 3: "refunding", 4: "refunded"}
    status_dist = {}
    for status_val, cnt in status_result.all():
        key = status_names.get(status_val, str(status_val))
        if key:
            status_dist[key] = cnt

    # 商品销量排行（本月，按销售额降序）
    goods_result = await db.execute(
        select(
            Good.title,
            func.coalesce(func.sum(Order.quantity), 0),
            func.coalesce(func.sum(Order.total_fee), 0),
        )
        .join(Order, Order.good_id == Good.id)
        .where(Order.status.in_(valid_status), Order.create_time >= month_start)
        .group_by(Good.id)
        .order_by(func.sum(Order.total_fee).desc())
        .limit(10)
    )
    top_goods = [
        {"title": title, "sales": int(sales), "revenue": int(rev)}
        for title, sales, rev in goods_result.all()
    ]

    return {"today": today, "month": month, "status_dist": status_dist, "top_goods": top_goods}


# ============================================================
# 聊天
# ============================================================

@app.get("/chat/conversations")
async def get_conversations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取会话列表（订单+咨询，按最后消息时间倒序）"""
    conversations = []

    # --- 订单会话 ---
    order_result = await db.execute(
        select(Order).options(selectinload(Order.good))
        .where(Order.customer_id == user.id)
    )
    for order in order_result.scalars().all():
        last_msg = await db.execute(
            select(ChatLog)
            .where(ChatLog.thread_type == "order", ChatLog.thread_id == order.id)
            .order_by(ChatLog.id.desc()).limit(1)
        )
        msg = last_msg.scalar_one_or_none()
        if msg:
            read_state = await db.execute(
                select(ChatReadState.last_read_id).where(
                    ChatReadState.user_id == user.id,
                    ChatReadState.thread_type == "order",
                    ChatReadState.thread_id == order.id,
                    ChatReadState.reader_role == user.role,
                )
            )
            last_read_id = read_state.scalar() or 0
            unread = await db.scalar(
                select(func.count()).select_from(ChatLog).where(
                    ChatLog.thread_type == "order",
                    ChatLog.thread_id == order.id,
                    ChatLog.id > last_read_id,
                    ChatLog.sender_role != user.role,
                )
            )
            conversations.append({
                "thread_type": "order",
                "thread_id": order.id,
                "create_time": order.create_time,
                "good_title": order.good.title if order.good else "商品",
                "good_img_url": order.good.img_url if order.good else "",
                "last_content": msg.content[:50],
                "last_time": msg.create_time,
                "last_msg_id": msg.id,
                "last_sender_role": msg.sender_role,
                "status": order.status,
                "unread_count": unread,
            })

    # --- 咨询会话 ---
    consult_result = await db.execute(
        select(Consultation).options(selectinload(Consultation.good))
        .where(Consultation.customer_id == user.id)
    )
    for consult in consult_result.scalars().all():
        last_msg = await db.execute(
            select(ChatLog)
            .where(ChatLog.thread_type == "consultation", ChatLog.thread_id == str(consult.id))
            .order_by(ChatLog.id.desc()).limit(1)
        )
        msg = last_msg.scalar_one_or_none()
        if msg:
            read_state = await db.execute(
                select(ChatReadState.last_read_id).where(
                    ChatReadState.user_id == user.id,
                    ChatReadState.thread_type == "consultation",
                    ChatReadState.thread_id == str(consult.id),
                    ChatReadState.reader_role == user.role,
                )
            )
            last_read_id = read_state.scalar() or 0
            unread = await db.scalar(
                select(func.count()).select_from(ChatLog).where(
                    ChatLog.thread_type == "consultation",
                    ChatLog.thread_id == str(consult.id),
                    ChatLog.id > last_read_id,
                    ChatLog.sender_role != user.role,
                )
            )
            conversations.append({
                "thread_type": "consultation",
                "thread_id": str(consult.id),
                "create_time": consult.create_time,
                "good_title": consult.good.title if consult.good else "商品",
                "good_img_url": consult.good.img_url if consult.good else "",
                "last_content": msg.content[:50],
                "last_time": msg.create_time,
                "last_msg_id": msg.id,
                "last_sender_role": msg.sender_role,
                "status": -1,
                "unread_count": unread,
            })

    conversations.sort(key=lambda x: x["last_time"], reverse=True)
    return conversations


@app.get("/chat/{thread_type}/{thread_id}", response_model=list[ChatLogOut])
async def get_chat(
    thread_type: str,
    thread_id: str,
    after_id: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_thread_access(thread_type, thread_id, user, db)
    result = await db.execute(
        select(ChatLog)
        .where(ChatLog.thread_type == thread_type, ChatLog.thread_id == thread_id, ChatLog.id > after_id)
        .order_by(ChatLog.create_time)
    )
    return result.scalars().all()


@app.post("/chat", response_model=ChatLogOut)
async def send_chat(
    data: ChatMessage,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _verify_thread_access(data.thread_type, data.thread_id, user, db)
    log = ChatLog(
        thread_type=data.thread_type,
        thread_id=data.thread_id,
        sender_id=user.id,
        sender_role=user.role,
        content=data.content,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@app.post("/chat/read/{thread_type}/{thread_id}")
async def mark_chat_read(
    thread_type: str,
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """标记该用户在此会话中已读（记录最新消息 id）"""
    await _verify_thread_access(thread_type, thread_id, user, db)
    last_msg = await db.execute(
        select(ChatLog).where(
            ChatLog.thread_type == thread_type, ChatLog.thread_id == thread_id
        ).order_by(ChatLog.id.desc()).limit(1)
    )
    msg = last_msg.scalar_one_or_none()
    if not msg:
        return {"ok": True}
    existing = await db.execute(
        select(ChatReadState).where(
            ChatReadState.user_id == user.id,
            ChatReadState.thread_type == thread_type,
            ChatReadState.thread_id == thread_id,
            ChatReadState.reader_role == user.role,
        )
    )
    state = existing.scalar_one_or_none()
    if state:
        state.last_read_id = msg.id
    else:
        state = ChatReadState(
            user_id=user.id, thread_type=thread_type,
            thread_id=thread_id, reader_role=user.role, last_read_id=msg.id
        )
        db.add(state)
    await db.commit()
    return {"ok": True}



# ============================================================
# 用户信息
# ============================================================

@app.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return user


# ============================================================
# 超级管理员（开发者页面，密码认证）
# ============================================================

async def verify_admin_key(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(401, "管理员密钥错误")
    return True


@app.post("/admin/login")
async def admin_login(data: AdminLogin):
    """管理员密码登录"""
    if data.password != settings.ADMIN_KEY:
        raise HTTPException(401, "密码错误")
    return {"token": data.password}


@app.get("/admin/users", response_model=list[UserOut])
async def admin_list_users(
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_admin_key),
):
    """获取所有用户列表"""
    result = await db.execute(select(User).order_by(User.id))
    return result.scalars().all()


@app.post("/admin/users", response_model=UserOut)
async def admin_create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_admin_key),
):
    """创建用户"""
    result = await db.execute(select(User).where(User.openid == data.openid))
    if result.scalar_one_or_none():
        raise HTTPException(400, "该 openid 已存在")
    user = User(
        openid=data.openid,
        role=data.role,
        nickname=data.nickname,
        phone=data.phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@app.put("/admin/users/{user_id}", response_model=UserOut)
async def admin_update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_admin_key),
):
    """更新用户信息/角色"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    await db.commit()
    await db.refresh(user)
    return user


@app.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_admin_key),
):
    """删除用户"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    await db.delete(user)
    await db.commit()
    return {"msg": "已删除"}


# ============================================================
# 本地测试：绕过 OAuth 直接登录
# ============================================================

@app.post("/test/login")
async def test_login(role: str = "CUSTOMER", db: AsyncSession = Depends(get_db)):
    """本地测试用：创建/获取测试用户，返回 token"""
    openid = f"test_{role.lower()}"
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(openid=openid, role=role, nickname=f"测试{role}")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return {"token": openid, "user": UserOut.model_validate(user)}


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

    # 快照页虚拟账号处理
    if data.get("is_snapshotuser") == 1:
        raise HTTPException(403, "当前为快照页模式，请点击「访问完整网页」后重试")

    # 用 OAuth access_token 获取用户昵称（snsapi_userinfo scope）
    nickname = ""
    oauth_token = data.get("access_token")
    if oauth_token:
        try:
            async with httpx.AsyncClient() as client:
                info_resp = await client.get(
                    "https://api.weixin.qq.com/sns/userinfo",
                    params={"access_token": oauth_token, "openid": openid, "lang": "zh_CN"},
                )
                info = info_resp.json()
                print(f"[AUTH] sns userinfo response: {info}")
                nickname = info.get("nickname", "")
        except Exception as e:
            print(f"[AUTH] get nickname failed: {e}")

    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(openid=openid, role=Role.CUSTOMER, nickname=nickname)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif nickname and not user.nickname:
        user.nickname = nickname
        await db.commit()

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
    user: User = Depends(require_role(Role.MERCHANT)),
):
    """商家创建自定义菜单"""
    result = await wx_create_menu(base_url)
    if result.get("errcode", 0) != 0:
        raise HTTPException(400, f"菜单创建失败: {result}")
    return {"msg": "菜单创建成功", "data": result}


# ============================================================
# 商家联系配置
# ============================================================

CONFIG_FILE = Path(__file__).parent / "contact_config.json"

def _load_contact_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"wechat": "", "phone": ""}


@app.get("/config/contact")
async def get_contact_config():
    """公开接口：获取商家联系方式"""
    return _load_contact_config()


@app.put("/config/contact")
async def update_contact_config(
    wechat: str = "",
    phone: str = "",
    x_admin_key: str = Header(..., alias="X-Admin-Key"),
):
    """管理员接口：更新商家联系方式"""
    if x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(401, "管理员密钥错误")
    cfg = {"wechat": wechat, "phone": phone}
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return {"msg": "已保存"}


@app.get("/config/frontend")
async def frontend_config():
    """前端配置：AppID、域名等"""
    return {"app_id": settings.APP_ID, "base_url": ""}


# ============================================================
# 前端页面
# ============================================================

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}


def _html(path: Path):
    """返回 HTML 页面，禁止缓存（iOS WKWebView 适配）"""
    return FileResponse(path, headers=NO_CACHE_HEADERS)


@app.get("/")
async def index_page():
    """统一入口：OAuth 登录后根据角色跳转"""
    return _html(FRONTEND_DIR / "index.html")


@app.get("/customer")
async def customer_page():
    return _html(FRONTEND_DIR / "customer.html")


@app.get("/merchant")
async def merchant_page():
    return _html(FRONTEND_DIR / "merchant.html")


@app.get("/admin")
async def admin_page():
    return _html(FRONTEND_DIR / "admin.html")


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


@app.get("/{verify_file}.txt")
async def wechat_verify_file(verify_file: str):
    """微信验证文件（根路径，如域名验证、业务域名验证）"""
    f = STATIC_DIR / f"{verify_file}.txt"
    if f.exists():
        return FileResponse(f, media_type="text/plain")
    raise HTTPException(404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
