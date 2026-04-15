"""微信自定义菜单管理"""

import httpx

from .token import get_access_token
from .config import settings


async def create_menu(base_url: str) -> dict:
    """
    创建服务号自定义菜单
    base_url: 服务部署的公网地址，如 https://wx.example.com
    """
    token = await get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/menu/create?access_token={token}"

    menu_data = {
        "button": [
            {
                "name": "预约按摩",
                "type": "view",
                "url": f"{base_url}/customer",
            },
            {
                "name": "商家管理",
                "type": "view",
                "url": f"{base_url}/merchant",
            },
            {
                "name": "客服中心",
                "type": "view",
                "url": f"{base_url}/service",
            },
        ]
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=menu_data)
        return resp.json()
