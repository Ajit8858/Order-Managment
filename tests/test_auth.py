import pytest

pytestmark = pytest.mark.asyncio


async def test_register_creates_user(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "SuperSecret123", "role": "customer"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "customer"
    assert "hashed_password" not in body


async def test_register_duplicate_email_rejected(client):
    payload = {"email": "bob@example.com", "password": "SuperSecret123", "role": "customer"}
    first = await client.post("/api/v1/auth/register", json=payload)
    second = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


async def test_login_success_returns_token_pair(client):
    await client.post("/api/v1/auth/register", json={"email": "carol@example.com", "password": "SuperSecret123"})
    resp = await client.post("/api/v1/auth/login", json={"email": "carol@example.com", "password": "SuperSecret123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_rejected(client):
    await client.post("/api/v1/auth/register", json={"email": "dave@example.com", "password": "SuperSecret123"})
    resp = await client.post("/api/v1/auth/login", json={"email": "dave@example.com", "password": "WrongPassword"})
    assert resp.status_code == 401


async def test_protected_route_requires_token(client):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_protected_route_with_valid_token(client):
    await client.post("/api/v1/auth/register", json={"email": "erin@example.com", "password": "SuperSecret123"})
    tokens = (await client.post("/api/v1/auth/login", json={"email": "erin@example.com", "password": "SuperSecret123"})).json()

    resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "erin@example.com"


async def test_cannot_self_register_as_admin(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "wannabe_admin@example.com", "password": "SuperSecret123", "role": "admin"},
    )
    assert resp.status_code == 403


async def test_refresh_token_rotation(client):
    await client.post("/api/v1/auth/register", json={"email": "frank@example.com", "password": "SuperSecret123"})
    tokens = (await client.post("/api/v1/auth/login", json={"email": "frank@example.com", "password": "SuperSecret123"})).json()

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["access_token"] != tokens["access_token"]

    # Old refresh token should now be revoked (rotation).
    reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 401
