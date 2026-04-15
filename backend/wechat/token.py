"""微信 Access Token 和 JS-SDK Ticket 全局缓存管理"""

import time
import hashlib
import random
import string
import asyncio

import httpx

from .config import settings

# 内存缓存
_token_cache: dict = {"access_token": "", "expires_at": 0}
_ticket_cache: dict = {"ticket": "", "expires_at": 0}
_lock = asyncio.Lock()


async def get_access_token() -> str:
    """获取全局 access_token，自动刷新"""
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    async with _lock:
        # double check
        if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
            return _token_cache["access_token"]

        url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": settings.APP_ID,
            "secret": settings.APP_SECRET,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        if "access_token" not in data:
            raise RuntimeError(f"获取 access_token 失败: {data}")

        _token_cache["access_token"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 7200) - 300
        return _token_cache["access_token"]


async def get_jsapi_ticket() -> str:
    """获取 jsapi_ticket，用于 JS-SDK 签名"""
    if _ticket_cache["ticket"] and time.time() < _ticket_cache["expires_at"]:
        return _ticket_cache["ticket"]

    token = await get_access_token()
    url = "https://api.weixin.qq.com/cgi-bin/ticket/getticket"
    params = {"access_token": token, "type": "jsapi"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        data = resp.json()

    if data.get("errcode") != 0:
        raise RuntimeError(f"获取 jsapi_ticket 失败: {data}")

    _ticket_cache["ticket"] = data["ticket"]
    _ticket_cache["expires_at"] = time.time() + data.get("expires_in", 7200) - 300
    return _ticket_cache["ticket"]


async def get_jssdk_signature(url: str) -> dict:
    """生成 JS-SDK 页面签名"""
    ticket = await get_jsapi_ticket()
    nonce_str = "".join(random.sample(string.ascii_letters + string.digits, 16))
    timestamp = str(int(time.time()))

    sign_str = f"jsapi_ticket={ticket}&noncestr={nonce_str}&timestamp={timestamp}&url={url}"
    signature = hashlib.sha1(sign_str.encode("utf-8")).hexdigest()

    return {
        "appId": settings.APP_ID,
        "timestamp": timestamp,
        "nonceStr": nonce_str,
        "signature": signature,
    }
