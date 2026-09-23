import uuid
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.payment import PaymentStatus


class PaymentCreate(BaseModel):
    order_id: uuid.UUID
    # Simulated card token — in a real integration this would be a Stripe/PSP token.
    card_token: str = "tok_test_success"


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    order_id: uuid.UUID
    amount: Decimal
    status: PaymentStatus
    provider: str
    transaction_ref: str
    retry_count: int
    failure_reason: str | None
    created_at: datetime
