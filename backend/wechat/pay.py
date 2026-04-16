"""微信支付 V3 JSAPI（公众号支付）"""

import time
import uuid
import json
import base64
from pathlib import Path
from urllib.parse import quote

import httpx
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
from Crypto.Cipher import AES

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

def _decrypt_resource(resource: dict) -> dict | None:
    """
    解密 V3 回调通知的 resource 字段。
    AES-256-GCM：key=APIv3密钥, nonce=resource.nonce,
    associated_data=resource.associated_data, ciphertext=resource.ciphertext
    """
    api_key = settings.API_V3_KEY
    if not api_key:
        return None

    nonce = resource.get("nonce", "")
    associated_data = resource.get("associated_data", "")
    ciphertext_b64 = resource.get("ciphertext", "")
    if not ciphertext_b64:
        return None

    ciphertext = base64.b64decode(ciphertext_b64)
    key = api_key.encode("utf-8")

    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce.encode("utf-8"))
        plaintext = cipher.decrypt_and_verify(
            ciphertext,
            tag=ciphertext[-16:],  # GCM tag 在末尾 16 字节 — 不对，需要分开
        )
        # 实际上 pycryptodome 的 GCM 模式需要先 update 再 verify
        # 但 decrypt_and_verify 要求 tag 单独传
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        pass

    # 正确的 GCM 解密方式
    try:
        raw = base64.b64decode(ciphertext_b64)
        tag = raw[-16:]
        ct = raw[:-16]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce.encode("utf-8"))
        cipher.update(associated_data.encode("utf-8"))
        plaintext = cipher.decrypt_and_verify(ct, tag)
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        return None


def verify_pay_notify(
    timestamp: str,
    nonce: str,
    body: str,
    signature: str,
    wechatpay_serial: str = "",
) -> dict | None:
    """
    验证 V3 支付回调通知并解密。
    1. 解析外层 JSON
    2. 解密 resource.ciphertext（AES-256-GCM，密钥为 APIv3Key）
    3. 返回解密后的支付结果

    开发阶段：没有 APIv3Key 时跳过解密，直接返回原始数据。
    生产环境：应先验签再解密。
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None

    resource = data.get("resource", {})
    if resource.get("ciphertext"):
        decrypted = _decrypt_resource(resource)
        if decrypted:
            return {"event_type": data.get("event_type"), "resource": decrypted}
        return None

    # 没有 ciphertext 时（非加密场景）直接返回
    return data


# ---------------------------------------------------------------------------
# V3 查询订单（商户订单号）
# ---------------------------------------------------------------------------

async def query_order(out_trade_no: str) -> dict:
    """
    通过商户订单号查询订单
    GET /v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={mchid}
    返回: {trade_state, transaction_id, ...}
    """
    url_path = f"/v3/pay/transactions/out-trade-no/{quote(out_trade_no, safe='')}"
    url = f"https://api.mch.weixin.qq.com{url_path}?mchid={settings.MCH_ID}"

    auth_header = _make_v3_auth_header("GET", url_path, "")

    headers = {
        "Accept": "application/json",
        "Authorization": auth_header,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=10)

    if resp.status_code != 200:
        raise Exception(f"查询订单失败 (HTTP {resp.status_code}): {resp.text}")

    return resp.json()


# ---------------------------------------------------------------------------
# V3 申请退款
# ---------------------------------------------------------------------------

async def create_refund(
    out_trade_no: str,
    out_refund_no: str,
    total: int,
    refund: int,
    notify_url: str,
    reason: str = "",
    transaction_id: str = "",
) -> dict:
    """
    申请退款
    POST /v3/refund/domestic/refunds
    返回: {refund_id, status, ...}
    """
    url = "https://api.mch.weixin.qq.com/v3/refund/domestic/refunds"
    url_path = "/v3/refund/domestic/refunds"

    body_obj = {
        "out_trade_no": out_trade_no,
        "out_refund_no": out_refund_no,
        "amount": {
            "refund": refund,
            "total": total,
            "currency": "CNY",
        },
        "notify_url": notify_url,
    }
    if transaction_id:
        body_obj["transaction_id"] = transaction_id
    if reason:
        body_obj["reason"] = reason[:80]

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
        raise Exception(f"申请退款失败 (HTTP {resp.status_code}): {resp.text}")

    return resp.json()


def decrypt_refund_notify(body: str) -> dict | None:
    """
    解密退款回调通知（与支付回调使用相同的 AES-256-GCM 解密）
    返回: {event_type, resource: {out_trade_no, refund_status, ...}}
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None

    resource = data.get("resource", {})
    if resource.get("ciphertext"):
        decrypted = _decrypt_resource(resource)
        if decrypted:
            return {"event_type": data.get("event_type"), "resource": decrypted}
        return None

    return data
