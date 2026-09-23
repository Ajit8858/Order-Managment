import math
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.database import get_db
from app.models.product import Product, Category
from app.models.user import User, UserRole
from app.schemas.product import (
    CategoryCreate,
    CategoryOut,
    PaginatedProducts,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from app.services.cache import (
    PRODUCT_KEY_PREFIX,
    PRODUCT_LIST_PREFIX,
    get_cached,
    invalidate_product_cache,
    set_cached,
)

router = APIRouter(prefix="/products", tags=["Products"])

SORTABLE_FIELDS = {"price": Product.price, "name": Product.name, "created_at": Product.created_at}


def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "-")


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
@router.post("/createcategories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    category = Category(name=payload.name, slug=_slugify(payload.name))
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
@router.post("/createproduct", response_model=ProductOut, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SELLER)),
):
    existing = await db.execute(select(Product).where(Product.sku == payload.sku))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU already exists")

    product = Product(**payload.model_dump(), seller_id=user.id)
    db.add(product)
    try:
        await db.commit()
    except:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product id is not present in category table")
        
    await db.refresh(product)
    await invalidate_product_cache()
    return product


@router.get("", response_model=PaginatedProducts)
async def list_products(
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = Query(None, description="Search by product name"),
    category_id: Optional[uuid.UUID] = None,
    min_price: Optional[Decimal] = Query(None, ge=0),
    max_price: Optional[Decimal] = Query(None, ge=0),
    sort_by: str = Query("created_at", pattern="^(price|name|created_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    cache_key = f"{PRODUCT_LIST_PREFIX}{q}:{category_id}:{min_price}:{max_price}:{sort_by}:{sort_dir}:{page}:{page_size}"
    cached = await get_cached(cache_key)
    if cached is not None:
        return PaginatedProducts(**cached)

    filters = [Product.is_active.is_(True)]
    if q:
        filters.append(Product.name.ilike(f"%{q}%"))
    if category_id:
        filters.append(Product.category_id == category_id)
    if min_price is not None:
        filters.append(Product.price >= min_price)
    if max_price is not None:
        filters.append(Product.price <= max_price)

    count_stmt = select(func.count()).select_from(Product).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    order_col = SORTABLE_FIELDS[sort_by]
    order_clause = asc(order_col) if sort_dir == "asc" else desc(order_col)

    stmt = (
        select(Product)
        .where(*filters)
        .order_by(order_clause)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(stmt)).scalars().all()

    result = PaginatedProducts(
        items=[ProductOut.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )
    await set_cached(cache_key, result.model_dump())
    return result


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cache_key = f"{PRODUCT_KEY_PREFIX}{product_id}"
    cached = await get_cached(cache_key)
    if cached is not None:
        return ProductOut(**cached)

    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    out = ProductOut.model_validate(product)
    await set_cached(cache_key, out.model_dump())
    return out


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SELLER)),
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if user.role == UserRole.SELLER and product.seller_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your product")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    await invalidate_product_cache(str(product_id))
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SELLER)),
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if user.role == UserRole.SELLER and product.seller_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your product")

    product.is_active = False  # soft delete: preserves history for existing orders
    await db.commit()
    await invalidate_product_cache(str(product_id))
    return None
