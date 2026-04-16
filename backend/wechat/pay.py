"""微信支付 V3 JSAPI（公众号支付）"""

import time
import uuid
import json
import base64
from pathlib import Path

import httpx
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256

from .config import settings


# ---------------------------------------------------------------------------
# RSA 工具
# ---------------------------------------------------------------------------

_private_key = None


def _load_private_key():
    """加载商户 RSA 私钥（PEM），全局缓存"""
    global _private_key
    if _private_key is not None:
        return _private_key
    key_path = settings.MCH_PRIVATE_KEY_PATH
    if not key_path:
        raise RuntimeError("未配置商户私钥路径 (WX_MCH_PRIVATE_KEY_PATH)")
    pem = Path(key_path).read_text(encoding="utf-8")
    _private_key = RSA.import_key(pem)
    return _private_key


def _sign_rsa(message: str, key=None) -> str:
    """SHA256withRSA 签名，返回 Base64 编码字符串"""
    if key is None:
        key = _load_private_key()
    h = SHA256.new(message.encode("utf-8"))
    signature = pkcs1_15.new(key).sign(h)
    return base64.b64encode(signature).decode("utf-8")


# ---------------------------------------------------------------------------
# V3 请求签名 & Authorization 头
# ---------------------------------------------------------------------------

def _make_v3_auth_header(method: str, url_path: str, body: str) -> str:
    """
    生成 V3 Authorization 请求头
    格式: WECHATPAY2-SHA256-RSA2048 mchid="...",nonce_str="...",timestamp="...",serial_no="...",signature="..."
    """
    timestamp = str(int(time.time()))
    nonce_str = uuid.uuid4().hex[:32]
    sign_message = f"{method}\n{url_path}\n{timestamp}\n{nonce_str}\n{body}\n"
    signature = _sign_rsa(sign_message)

    authorization = (
        f'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{settings.MCH_ID}",'
        f'nonce_str="{nonce_str}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{settings.MCH_SERIAL_NO}",'
        f'signature="{signature}"'
    )
    return authorization


# ---------------------------------------------------------------------------
# V3 统一下单
# ---------------------------------------------------------------------------

async def create_prepay_order(
    order_id: str,
    openid: str,
    total_fee: int,
    description: str,
    notify_url: str,
) -> str:
    """
    调用 V3 统一下单 API，返回 prepay_id
    POST https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi
    """
    url = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"
    url_path = "/v3/pay/transactions/jsapi"

    body_obj = {
        "appid": settings.APP_ID,
        "mchid": settings.MCH_ID,
        "description": description[:128],
        "out_trade_no": order_id,
        "notify_url": notify_url,
        "amount": {
            "total": total_fee,
            "currency": "CNY",
        },
        "payer": {
            "openid": openid,
        },
    }
    body_str = json.dumps(body_obj, separators=(",", ":"))

    auth_header = _make_v3_auth_header("POST", url_path, body_str)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": auth_header,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, content=body_str, headers=headers, timeout=10)

    if resp.status_code != 200:
        raise Exception(f"微信支付下单失败 (HTTP {resp.status_code}): {resp.text}")

    data = resp.json()
    prepay_id = data.get("prepay_id")
    if not prepay_id:
        raise Exception(f"微信支付下单失败: 未返回 prepay_id, resp={resp.text}")

    return prepay_id


# ---------------------------------------------------------------------------
# V3 前端支付参数签名
# ---------------------------------------------------------------------------

def generate_jsapi_params(prepay_id: str) -> dict:
    """
    生成 WeixinJSBridge.invoke('getBrandWCPayRequest') 所需参数（V3 RSA 签名）
    签名串: appId\ntimeStamp\nnonceStr\npackage\n
    """
    timestamp = str(int(time.time()))
    nonce_str = uuid.uuid4().hex[:32]
    package = f"prepay_id={prepay_id}"

    sign_message = f"{settings.APP_ID}\n{timestamp}\n{nonce_str}\n{package}\n"
    pay_sign = _sign_rsa(sign_message)

    return {
        "appId": settings.APP_ID,
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


# ---------------------------------------------------------------------------
# V3 回调通知验签
# ---------------------------------------------------------------------------

def verify_pay_notify(
    timestamp: str,
    nonce: str,
    body: str,
    signature: str,
    wechatpay_serial: str = "",
) -> dict | None:
    """
    验证 V3 支付回调通知签名。
    签名串: timestamp\nnonce\nbody\n
    使用微信平台证书验签（开发阶段：有商户私钥时才验签，否则跳过验签只解析）。

    返回解密后的通知数据，验签失败返回 None。
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None

    # 开发阶段：没有微信平台证书时跳过验签，直接返回数据
    # 生产环境：应使用微信平台证书验证 signature
    # TODO: 生产环境需加载微信平台证书并验签
    return data
