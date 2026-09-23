from typing import AsyncGenerator

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app import redis_client as redis_module
from app.models.cart import Cart
from app.models.user import User, UserRole

TEST_DATABASE_URL = "sqlite+aiosqlite://"  # in-memory, shared connection via StaticPool

engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True, scope="session")
def _patch_redis():
    """Swap the real Redis client for an in-memory fake so tests don't need
    a running Redis instance, while caching/rate-limiting still work."""
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis_module.redis_client = fake

    import app.core.rate_limit as rl
    import app.services.cache as cache_module
    rl.redis_client = fake
    cache_module.redis_client = fake
    yield fake


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def register_and_login(client: AsyncClient, email: str, password: str = "SuperSecret123", role: str = "customer") -> dict:
    """For customer/seller roles, goes through the real public register+login flow.

    Admin accounts can't self-register (see auth.py), so for role="admin" this
    seeds the user directly into the test DB — mirroring how an admin would be
    provisioned out-of-band in production — then logs in normally.
    """
    if role == "admin":
        async with TestSessionLocal() as session:
            user = User(email=email, hashed_password=hash_password(password), role=UserRole.ADMIN)
            session.add(user)
            await session.flush()
            session.add(Cart(user_id=user.id))
            await session.commit()
    else:
        await client.post("/api/v1/auth/register", json={"email": email, "password": password, "role": role})

    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()
