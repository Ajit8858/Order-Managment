import pytest

from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def test_admin_only_user_list_blocked_for_customer(client):
    tokens = await register_and_login(client, "perm1@example.com", role="customer")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 403


async def test_admin_only_user_list_allowed_for_admin(client):
    tokens = await register_and_login(client, "perm2@example.com", role="admin")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 200


async def test_seller_cannot_edit_other_sellers_product(client):
    seller1_tokens = await register_and_login(client, "seller1@example.com", role="seller")
    seller1_headers = {"Authorization": f"Bearer {seller1_tokens['access_token']}"}
    product = (
        await client.post(
            "/api/v1/products",
            json={"name": "Seller1 Item", "price": "10.00", "stock": 5, "sku": "SKU-S1"},
            headers=seller1_headers,
        )
    ).json()

    seller2_tokens = await register_and_login(client, "seller2@example.com", role="seller")
    seller2_headers = {"Authorization": f"Bearer {seller2_tokens['access_token']}"}

    resp = await client.patch(f"/api/v1/products/{product['id']}", json={"price": "999.00"}, headers=seller2_headers)
    assert resp.status_code == 403


async def test_customer_cannot_view_other_customers_order(client):
    admin_tokens = await register_and_login(client, "perm_admin@example.com", role="admin")
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    product = (
        await client.post(
            "/api/v1/products",
            json={"name": "Shared Item", "price": "10.00", "stock": 5, "sku": "SKU-SHARED"},
            headers=admin_headers,
        )
    ).json()

    owner_tokens = await register_and_login(client, "owner@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_tokens['access_token']}"}
    await client.post("/api/v1/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=owner_headers)
    order = (await client.post("/api/v1/orders", headers=owner_headers)).json()

    stranger_tokens = await register_and_login(client, "stranger@example.com")
    stranger_headers = {"Authorization": f"Bearer {stranger_tokens['access_token']}"}

    resp = await client.get(f"/api/v1/orders/{order['id']}", headers=stranger_headers)
    assert resp.status_code == 403


async def test_unauthenticated_cannot_access_cart(client):
    resp = await client.get("/api/v1/cart")
    assert resp.status_code == 401
