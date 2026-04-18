import pytest


@pytest.mark.asyncio
async def test_admin_can_create_update_and_delete_merchant_contacts(client, admin_headers):
    created = await client.post(
        "/admin/merchant-contacts",
        json={
            "name": "夜班客服",
            "wechat": "night_shift",
            "phone": "13900000099",
            "is_active": True,
            "sort_order": 30,
        },
        headers=admin_headers,
    )
    assert created.status_code == 200
    contact_id = created.json()["id"]

    listed = await client.get("/admin/merchant-contacts", headers=admin_headers)
    assert listed.status_code == 200
    assert any(item["id"] == contact_id for item in listed.json())

    updated = await client.put(
        f"/admin/merchant-contacts/{contact_id}",
        json={"name": "夜班客服(调整)", "is_active": False},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "夜班客服(调整)"
    assert updated.json()["is_active"] is False

    deleted = await client.delete(f"/admin/merchant-contacts/{contact_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
