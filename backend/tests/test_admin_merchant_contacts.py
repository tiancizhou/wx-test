import pytest


@pytest.mark.asyncio
async def test_admin_can_create_update_and_delete_merchant_users(client, admin_headers):
    created = await client.post(
        "/admin/users",
        json={
            "openid": "merchant_created_for_admin_test",
            "nickname": "商家夜班",
            "phone": "13900000099",
            "role": "MERCHANT",
        },
        headers=admin_headers,
    )
    assert created.status_code == 200
    user_id = created.json()["id"]
    assert created.json()["role"] == "MERCHANT"

    listed = await client.get("/admin/users", headers=admin_headers)
    assert listed.status_code == 200
    merchants = [item for item in listed.json() if item["role"] == "MERCHANT"]
    assert any(item["id"] == user_id for item in merchants)

    updated = await client.put(
        f"/admin/users/{user_id}",
        json={"nickname": "商家夜班(调整)", "phone": "13900000111", "role": "MERCHANT"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["nickname"] == "商家夜班(调整)"
    assert updated.json()["role"] == "MERCHANT"

    deleted = await client.delete(f"/admin/users/{user_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"msg": "已删除"}
