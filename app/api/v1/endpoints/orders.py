import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_active_user, require_roles
from app.database import get_db
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.order import OrderOut, OrderStatusUpdate, PaginatedOrders
from app.services.cache import invalidate_product_cache
from app.services.order_state import assert_valid_transition

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Checkout: converts the current cart into an order.

    Runs as a single DB transaction with row-level locking on the products
    being purchased, so two concurrent checkouts can't both oversell the
    last unit of stock.
    """
    cart_stmt = (
        select(Cart)
        .where(Cart.user_id == user.id)
        .options(selectinload(Cart.items).selectinload(CartItem.product))
    )
    cart = (await db.execute(cart_stmt)).scalar_one_or_none()
    if cart is None or not cart.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    product_ids = [item.product_id for item in cart.items]
    # SELECT ... FOR UPDATE locks these rows until commit, preventing a race
    # between two simultaneous checkouts on the same product.
    locked_products = {
        p.id: p
        for p in (
            await db.execute(select(Product).where(Product.id.in_(product_ids)).with_for_update())
        ).scalars()
    }

    total = 0
    order_items = []
    for cart_item in cart.items:
        product = locked_products[cart_item.product_id]
        if product.stock < cart_item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for '{product.name}' (available: {product.stock})",
            )
        product.stock -= cart_item.quantity
        total += product.price * cart_item.quantity
        order_items.append(OrderItem(product_id=product.id, quantity=cart_item.quantity, unit_price=product.price))

    order = Order(user_id=user.id, status=OrderStatus.PENDING, total_amount=total, items=order_items)
    db.add(order)

    for cart_item in cart.items:
        await db.delete(cart_item)

    await db.commit()

    for pid in product_ids:
        await invalidate_product_cache(str(pid))

    reload_stmt = select(Order).where(Order.id == order.id).options(selectinload(Order.items).selectinload(OrderItem.product))
    order = (await db.execute(reload_stmt)).scalar_one()
    return order


@router.get("", response_model=PaginatedOrders)
async def list_my_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    filters = [Order.user_id == user.id]
    total = (await db.execute(select(func.count()).select_from(Order).where(*filters))).scalar_one()

    stmt = (
        select(Order)
        .where(*filters)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(stmt)).scalars().all()

    return PaginatedOrders(
        items=items, total=total, page=page, page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.items).selectinload(OrderItem.product))
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.user_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")
    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: uuid.UUID,
    payload: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SELLER)),
):
    """Admin/seller-only: advance an order along the shipping pipeline
    (ORDER_CONFIRMED -> SHIPPED -> DELIVERED), validated against the state machine.
    """
    stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.items).selectinload(OrderItem.product))
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    assert_valid_transition(order.status, payload.status)
    order.status = payload.status
    await db.commit()
    await db.refresh(order)
    return order


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.items).selectinload(OrderItem.product))
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.user_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")

    assert_valid_transition(order.status, OrderStatus.CANCELLED)

    # Restock items being cancelled.
    for item in order.items:
        product = await db.get(Product, item.product_id)
        if product:
            product.stock += item.quantity

    order.status = OrderStatus.CANCELLED
    await db.commit()

    for item in order.items:
        await invalidate_product_cache(str(item.product_id))

    await db.refresh(order)
    return order
