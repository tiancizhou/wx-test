import pytest

from wechat.config import settings


@pytest.mark.asyncio
async def test_frontend_config_returns_configured_app_id(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ID", "wx-configured-appid")

    response = await client.get("/config/frontend")

    assert response.status_code == 200
    assert response.json() == {"app_id": "wx-configured-appid", "base_url": ""}


@pytest.mark.asyncio
async def test_frontend_config_returns_503_when_app_id_is_blank(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ID", "   ")

    response = await client.get("/config/frontend")

    assert response.status_code == 503
    assert response.json() == {"detail": "WX_APP_ID 未配置"}
