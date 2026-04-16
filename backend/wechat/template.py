"""微信模板消息发送"""

import httpx

from .token import get_access_token


async def send_template_msg(
    openid: str,
    template_id: str,
    data: dict,
    url: str = "",
    miniprogram: dict = None,
) -> dict:
    """
    发送模板消息
    openid: 接收用户 openid
    template_id: 模板 ID（在微信后台申请）
    data: 模板数据，如 {"first": {"value":"xxx"}, "keyword1": {"value":"xxx"}, ...}
    url: 点击模板卡片后的跳转页（可选）
    """
    access_token = await get_access_token()
    api_url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"

    payload = {
        "touser": openid,
        "template_id": template_id,
        "data": data,
    }
    if url:
        payload["url"] = url
    if miniprogram:
        payload["miniprogram"] = miniprogram

    async with httpx.AsyncClient() as client:
        resp = await client.post(api_url, json=payload)
        return resp.json()


# ---- 业务场景封装 ----

async def notify_order_completed(openid: str, order_id: str):
    """通知客户：服务已完成"""
    template_id = "YOUR_TEMPLATE_ID_COMPLETE"  # 需替换为微信后台申请的模板 ID
    await send_template_msg(
        openid=openid,
        template_id=template_id,
        data={
            "first": {"value": "服务已完成，感谢您的使用"},
            "keyword1": {"value": order_id},
            "keyword2": {"value": "已完成"},
            "remark": {"value": "欢迎再次预约"},
        },
    )
