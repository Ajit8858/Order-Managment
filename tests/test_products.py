import pytest

from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email, role="admin"):
    tokens = await register_and_login(client, email, role=role)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_admin_can_create_product(client):
    headers = await _auth_headers(client, "admin1@example.com", role="admin")
    resp = await client.post(
        "/api/v1/products",
        json={"name": "Wireless Mouse", "price": "19.99", "stock": 50, "sku": "SKU-001"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Wireless Mouse"
    assert body["stock"] == 50


async def test_customer_cannot_create_product(client):
    headers = await _auth_headers(client, "cust1@example.com", role="customer")
    resp = await client.post(
        "/api/v1/products",
        json={"name": "Keyboard", "price": "29.99", "stock": 10, "sku": "SKU-002"},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_duplicate_sku_rejected(client):
    headers = await _auth_headers(client, "admin2@example.com", role="admin")
    payload = {"name": "Monitor", "price": "199.99", "stock": 5, "sku": "SKU-DUP"}
    first = await client.post("/api/v1/products", json=payload, headers=headers)
    second = await client.post("/api/v1/products", json=payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 409


async def test_list_products_search_and_pagination(client):
    headers = await _auth_headers(client, "admin3@example.com", role="admin")
    for i in range(5):
        await client.post(
            "/api/v1/products",
            json={"name": f"Gadget {i}", "price": f"{10 + i}.00", "stock": 10, "sku": f"SKU-G{i}"},
            headers=headers,
        )
    await client.post(
        "/api/v1/products",
        json={"name": "Totally Different Item", "price": "5.00", "stock": 10, "sku": "SKU-DIFF"},
        headers=headers,
    )

    resp = await client.get("/api/v1/products", params={"q": "Gadget", "page": 1, "page_size": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 3
    assert body["pages"] == 2


async def test_list_products_sort_by_price(client):
    headers = await _auth_headers(client, "admin4@example.com", role="admin")
    await client.post("/api/v1/products", json={"name": "Cheap", "price": "5.00", "stock": 1, "sku": "SKU-CHEAP"}, headers=headers)
    await client.post("/api/v1/products", json={"name": "Pricey", "price": "500.00", "stock": 1, "sku": "SKU-PRICEY"}, headers=headers)

    resp = await client.get("/api/v1/products", params={"sort_by": "price", "sort_dir": "asc"})
    prices = [float(p["price"]) for p in resp.json()["items"]]
    assert prices == sorted(prices)


async def test_get_nonexistent_product_404(client):
    resp = await client.get("/api/v1/products/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
