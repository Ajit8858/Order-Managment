import pytest

from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def _make_product(client, admin_headers, stock=10, price="25.00", sku="SKU-ORD"):
    resp = await client.post(
        "/api/v1/products",
        json={"name": "Test Product", "price": price, "stock": stock, "sku": sku},
        headers=admin_headers,
    )
    return resp.json()


async def test_checkout_creates_order_and_deducts_stock(client):
    admin_tokens = await register_and_login(client, "admin_o1@example.com", role="admin")
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    product = await _make_product(client, admin_headers, stock=10)

    cust_tokens = await register_and_login(client, "cust_o1@example.com")
    cust_headers = {"Authorization": f"Bearer {cust_tokens['access_token']}"}

    await client.post("/api/v1/cart/items", json={"product_id": product["id"], "quantity": 3}, headers=cust_headers)
    resp = await client.post("/api/v1/orders", headers=cust_headers)

    assert resp.status_code == 201
    order = resp.json()
    assert order["status"] == "PENDING"
    assert float(order["total_amount"]) == 75.00

    product_after = (await client.get(f"/api/v1/products/{product['id']}", headers=cust_headers)).json()
    assert product_after["stock"] == 7


async def test_checkout_fails_on_empty_cart(client):
    tokens = await register_and_login(client, "cust_o2@example.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = await client.post("/api/v1/orders", headers=headers)
    assert resp.status_code == 400


async def test_checkout_fails_when_stock_insufficient(client):
    admin_tokens = await register_and_login(client, "admin_o2@example.com", role="admin")
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    product = await _make_product(client, admin_headers, stock=2, sku="SKU-LOW")

    cust_tokens = await register_and_login(client, "cust_o3@example.com")
    cust_headers = {"Authorization": f"Bearer {cust_tokens['access_token']}"}

    add_resp = await client.post("/api/v1/cart/items", json={"product_id": product["id"], "quantity": 2}, headers=cust_headers)
    assert add_resp.status_code == 201

    # Manually push cart quantity beyond stock via a second add to simulate a race/edit.
    cart = (await client.get("/api/v1/cart", headers=cust_headers)).json()
    item_id = cart["items"][0]["id"]
    await client.patch(f"/api/v1/cart/items/{item_id}", json={"quantity": 2}, headers=cust_headers)

    # Reduce stock out from under the cart via admin update, then attempt checkout.
    await client.patch(f"/api/v1/products/{product['id']}", json={"stock": 1}, headers=admin_headers)

    resp = await client.post("/api/v1/orders", headers=cust_headers)
    assert resp.status_code == 400


async def test_full_payment_success_flow_confirms_order(client):
    admin_tokens = await register_and_login(client, "admin_o3@example.com", role="admin")
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    product = await _make_product(client, admin_headers, stock=5, sku="SKU-PAY-OK")

    cust_tokens = await register_and_login(client, "cust_o4@example.com")
    cust_headers = {"Authorization": f"Bearer {cust_tokens['access_token']}"}

    await client.post("/api/v1/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=cust_headers)
    order = (await client.post("/api/v1/orders", headers=cust_headers)).json()

    pay_resp = await client.post(
        "/api/v1/payments", json={"order_id": order["id"], "card_token": "tok_test_success"}, headers=cust_headers
    )
    assert pay_resp.status_code == 201
    assert pay_resp.json()["status"] == "SUCCESS"

    order_after = (await client.get(f"/api/v1/orders/{order['id']}", headers=cust_headers)).json()
    assert order_after["status"] == "ORDER_CONFIRMED"


async def test_payment_failure_flow(client):
    admin_tokens = await register_and_login(client, "admin_o4@example.com", role="admin")
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    product = await _make_product(client, admin_headers, stock=5, sku="SKU-PAY-FAIL")

    cust_tokens = await register_and_login(client, "cust_o5@example.com")
    cust_headers = {"Authorization": f"Bearer {cust_tokens['access_token']}"}

    await client.post("/api/v1/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=cust_headers)
    order = (await client.post("/api/v1/orders", headers=cust_headers)).json()

    pay_resp = await client.post(
        "/api/v1/payments", json={"order_id": order["id"], "card_token": "tok_test_fail"}, headers=cust_headers
    )
    assert pay_resp.status_code == 201
    assert pay_resp.json()["status"] == "FAILED"

    order_after = (await client.get(f"/api/v1/orders/{order['id']}", headers=cust_headers)).json()
    assert order_after["status"] == "PAYMENT_FAILED"

    # Order should now be payable again (retry).
    retry_resp = await client.post(
        "/api/v1/payments", json={"order_id": order["id"], "card_token": "tok_test_success"}, headers=cust_headers
    )
    assert retry_resp.status_code == 201
    assert retry_resp.json()["status"] == "SUCCESS"


async def test_invalid_status_transition_rejected(client):
    admin_tokens = await register_and_login(client, "admin_o5@example.com", role="admin")
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    product = await _make_product(client, admin_headers, stock=5, sku="SKU-TRANS")

    cust_tokens = await register_and_login(client, "cust_o6@example.com")
    cust_headers = {"Authorization": f"Bearer {cust_tokens['access_token']}"}

    await client.post("/api/v1/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=cust_headers)
    order = (await client.post("/api/v1/orders", headers=cust_headers)).json()

    # PENDING -> SHIPPED is not a legal transition (must go through payment/confirmation first).
    resp = await client.patch(f"/api/v1/orders/{order['id']}/status", json={"status": "SHIPPED"}, headers=admin_headers)
    assert resp.status_code == 400
