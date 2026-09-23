# Order Management Backend

An end-to-end e-commerce order-management API built with **FastAPI**, **PostgreSQL**,
**Redis**, and **Celery**.

## Features

- **Auth**: register/login, JWT access + refresh tokens (refresh tokens are hashed at
  rest and rotated on use), bcrypt password hashing, role-based access control
  (`customer`, `admin`, `seller`).
- **Products**: CRUD, category tagging, full-text-ish search (`q`), filtering by
  category/price range, sorting, pagination, and Redis-backed caching with
  invalidation on writes.
- **Cart & Orders**: add/update/remove cart items, checkout that converts a cart into
  an order inside a single DB transaction with `SELECT ... FOR UPDATE` row locking
  (prevents overselling under concurrent checkouts), order history with pagination,
  and a validated order status state machine:

  ```
  PENDING → PAYMENT_SUCCESS → ORDER_CONFIRMED → SHIPPED → DELIVERED
      ↓            ↓                ↓
  PAYMENT_FAILED  CANCELLED      CANCELLED
  ```

- **Simulated payment gateway**: deterministic success/failure (a card token ending
  in `fail` always fails), retry limit, automatic order confirmation on success,
  and background email dispatch either way.
- **Redis**: product/category caching, sliding-window rate limiting on auth/write
  endpoints.
- **Celery**: order-confirmation & payment-failure emails, PDF invoice generation
  (ReportLab), inventory low-stock logging, and scheduled cleanup jobs (expired
  refresh tokens, stale unpaid orders) via Celery Beat.
- **PostgreSQL**: foreign keys with `ON DELETE` semantics, composite indexes for
  common query patterns, transactions with row locking, joined eager loading, and
  aggregate queries (counts for pagination).
- **Docs**: Swagger UI at `/docs`, ReDoc at `/redoc`, raw schema at `/openapi.json`.
- **Tests**: `pytest` + `httpx.AsyncClient` against an in-memory SQLite DB and a
  fake Redis, covering auth, product APIs, checkout/payment flows, and
  permission boundaries.

## Project layout

```
app/
  main.py              FastAPI app, middleware, exception handlers
  config.py            Settings (env-driven)
  database.py           Async SQLAlchemy engine/session
  redis_client.py       Async Redis client
  celery_app.py         Celery app + beat schedule
  models/               SQLAlchemy ORM models
  schemas/               Pydantic request/response schemas
  core/                  security (JWT/bcrypt), deps (auth/RBAC), rate limiting
  services/              Redis caching, order state-machine validation
  tasks/                 Celery tasks (email, invoice, inventory, cleanup)
  api/v1/endpoints/       Route handlers (auth, users, products, cart, orders, payments)
alembic/                 DB migrations
tests/                   pytest suite
docker-compose.yml       Postgres + Redis + API + Celery worker/beat + Flower
```

## Running locally with Docker (recommended)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000/docs
- Flower (Celery monitoring): http://localhost:5555

The API container auto-creates tables on startup in development mode. For a
production-style flow, generate and apply an Alembic migration instead:

```bash
docker compose exec api alembic revision --autogenerate -m "init"
docker compose exec api alembic upgrade head
```

## Running locally without Docker

Requires a running PostgreSQL and Redis instance (update `.env` accordingly).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
uvicorn app.main:app --reload

# In separate terminals:
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat --loglevel=info
```

## Running tests

Tests run against an in-memory SQLite DB and a fake Redis — no external services
required:

```bash
pip install -r requirements.txt
pytest -v
```

## Example flow

Note: `role: "admin"` is rejected by `/auth/register` on purpose (see "Notes on
design decisions" below) — seed an admin directly in the DB, or register as
`"seller"` for the product-creation step below.

```bash
# Register + login (as a seller, since sellers can also create products)
curl -X POST localhost:8000/api/v1/auth/register -H "Content-Type: application/json" \
  -d '{"email": "seller@example.com", "password": "SuperSecret123", "role": "seller"}'
curl -X POST localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email": "seller@example.com", "password": "SuperSecret123"}'
# -> copy access_token into Authorization: Bearer <token> for the calls below

# Create a product (admin/seller only)
curl -X POST localhost:8000/api/v1/products -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Widget", "price": "9.99", "stock": 100, "sku": "SKU-1"}'

# Add to cart, checkout, pay
curl -X POST localhost:8000/api/v1/cart/items -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" -d '{"product_id": "<id>", "quantity": 2}'
curl -X POST localhost:8000/api/v1/orders -H "Authorization: Bearer <token>"
curl -X POST localhost:8000/api/v1/payments -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" -d '{"order_id": "<order_id>", "card_token": "tok_test_success"}'
```

## Notes on design decisions

- **Cross-DB UUID type**: models use SQLAlchemy's generic `Uuid` type (not
  `postgresql.UUID`) so the same model code runs against SQLite in tests and
  native `UUID` in Postgres in production.
- **Soft-delete for products**: deleting a product sets `is_active = False` rather
  than removing the row, since past orders reference it via foreign key.
- **Price snapshotting**: `OrderItem.unit_price` stores the price at purchase time,
  so later price changes don't retroactively alter historical order totals.
- **Refresh token rotation**: each refresh call revokes the old token and issues a
  new pair, limiting the blast radius of a leaked refresh token.
- **No public admin self-registration**: `/auth/register` rejects `role: "admin"`;
  admin accounts are seeded directly (see `tests/conftest.py`'s `register_and_login`
  helper for the pattern) or provisioned via an internal tool in a real deployment.
