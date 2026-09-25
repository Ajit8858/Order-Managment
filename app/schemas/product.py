import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    price: Decimal = Field(gt=0)
    stock: int = Field(ge=0)
    sku: str = Field(min_length=1, max_length=64)
    image_url: Optional[str] = Field(default=None, max_length=1000)
    category_id: Optional[uuid.UUID] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, gt=0)
    stock: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    image_url: Optional[str] = Field(default=None, max_length=1000)
    category_id: Optional[uuid.UUID] = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    price: Decimal
    stock: int
    sku: str
    image_url: Optional[str]
    is_active: bool
    category_id: Optional[uuid.UUID]
    seller_id: Optional[uuid.UUID]
    created_at: datetime


class PaginatedProducts(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    pages: int
