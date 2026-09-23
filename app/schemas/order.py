import uuid
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.order import OrderStatus
from app.schemas.product import ProductOut


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product: ProductOut
    quantity: int
    unit_price: Decimal


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: OrderStatus
    total_amount: Decimal
    items: list[OrderItemOut]
    created_at: datetime
    updated_at: datetime


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class PaginatedOrders(BaseModel):
    items: list[OrderOut]
    total: int
    page: int
    page_size: int
    pages: int
