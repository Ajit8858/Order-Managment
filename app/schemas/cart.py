import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict

from app.schemas.product import ProductOut


class CartItemAdd(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product: ProductOut
    quantity: int

    @property
    def subtotal(self) -> Decimal:
        return self.product.price * self.quantity


class CartOut(BaseModel):
    id: uuid.UUID
    items: list[CartItemOut]
    total: Decimal
