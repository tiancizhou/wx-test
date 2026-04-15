"""微信支付 JSAPI（公众号支付）"""

import time
import hashlib
import uuid
import xml.etree.cElementTree as ET

import httpx

from .config import settings


def _make_sign(params: dict, key: str) -> str:
    """生成微信支付签名"""
    sorted_params = sorted(params.items())
    sign_str = "&".join(f"{k}={v}" for k, v in sorted_params if v) + f"&key={key}"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()


def _to_xml(params: dict) -> str:
    """dict → XML"""
    xml_parts = ["<xml>"]
    for k, v in params.items():
        xml_parts.append(f"<{k}><![CDATA[{v}]]></{k}>")
    xml_parts.append("</xml>")
    return "".join(xml_parts)


def _from_xml(xml_str: str) -> dict:
    """XML → dict"""
    root = ET.fromstring(xml_str)
    return {child.tag: child.text or "" for child in root}


async def create_prepay_order(
    order_id: str,
    openid: str,
    total_fee: int,
    description: str,
    notify_url: str,
) -> str:
    """
    调用统一下单 API，返回 prepay_id
    """
    base_url = "https://api.mch.weixin.qq.com"
    if not settings.MCH_ID:
        # 无商户号时使用沙盒 URL
        base_url = "https://api.mch.weixin.qq.com/sandboxnew"

    params = {
        "appid": settings.APP_ID,
        "mch_id": settings.MCH_ID or "1900000000",
        "nonce_str": uuid.uuid4().hex[:32],
        "body": description[:128],
        "out_trade_no": order_id,
        "total_fee": str(total_fee),
        "spbill_create_ip": "127.0.0.1",
        "notify_url": notify_url,
        "trade_type": "JSAPI",
        "openid": openid,
    }
    params["sign"] = _make_sign(params, settings.MCH_KEY or "sandbox_key")

    url = f"{base_url}/pay/unifiedorder"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, content=_to_xml(params), timeout=10)
        data = _from_xml(resp.text)

    if data.get("return_code") != "SUCCESS" or data.get("result_code") != "SUCCESS":
        err = data.get("return_msg") or data.get("err_code_des") or "统一下单失败"
        raise Exception(f"微信支付下单失败: {err}")

    return data["prepay_id"]


def generate_jsapi_params(prepay_id: str) -> dict:
    """
    生成 wx.requestPayment() 所需的参数
    """
    params = {
        "appId": settings.APP_ID,
        "timeStamp": str(int(time.time())),
        "nonceStr": uuid.uuid4().hex[:32],
        "package": f"prepay_id={prepay_id}",
        "signType": "MD5",
    }
    params["paySign"] = _make_sign(params, settings.MCH_KEY or "sandbox_key")
    return params


def verify_pay_notify(xml_data: str) -> dict | None:
    """
    验证支付回调通知签名，返回解析后的数据，验签失败返回 None
    """
    data = _from_xml(xml_data)
    sign = data.pop("sign", "")
    if not sign:
        return None
    expected = _make_sign(data, settings.MCH_KEY or "sandbox_key")
    if sign != expected:
        return None
    return data
