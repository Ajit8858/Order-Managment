import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_active_user
from app.database import get_db
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.models.user import User
from app.schemas.cart import CartItemAdd, CartItemUpdate, CartOut

router = APIRouter(prefix="/cart", tags=["Cart"])


async def _get_or_create_cart(db: AsyncSession, user: User) -> Cart:
    stmt = select(Cart).where(Cart.user_id == user.id).options(selectinload(Cart.items).selectinload(CartItem.product))
    cart = (await db.execute(stmt)).scalar_one_or_none()
    if cart is None:
        cart = Cart(user_id=user.id)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)
        cart.items = []
    return cart


def _serialize(cart: Cart) -> CartOut:
    total = sum((item.product.price * item.quantity for item in cart.items), start=0)
    return CartOut(id=cart.id, items=cart.items, total=total)


@router.get("", response_model=CartOut)
async def view_cart(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    cart = await _get_or_create_cart(db, user)
    return _serialize(cart)


@router.post("/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
async def add_item(
    payload: CartItemAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    product = await db.get(Product, payload.product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.stock < payload.quantity:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient stock")

    cart = await _get_or_create_cart(db, user)

    existing_item = next((i for i in cart.items if i.product_id == payload.product_id), None)
    if existing_item:
        existing_item.quantity += payload.quantity
    else:
        db.add(CartItem(cart_id=cart.id, product_id=payload.product_id, quantity=payload.quantity))

    await db.commit()
    cart = await _get_or_create_cart(db, user)
    return _serialize(cart)


@router.patch("/items/{item_id}", response_model=CartOut)
async def update_item(
    item_id: uuid.UUID,
    payload: CartItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    cart = await _get_or_create_cart(db, user)
    item = next((i for i in cart.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    if item.product.stock < payload.quantity:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient stock")

    item.quantity = payload.quantity
    await db.commit()
    cart = await _get_or_create_cart(db, user)
    return _serialize(cart)


@router.delete("/items/{item_id}", response_model=CartOut)
async def remove_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    cart = await _get_or_create_cart(db, user)
    item = next((i for i in cart.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    await db.delete(item)
    await db.commit()
    cart = await _get_or_create_cart(db, user)
    return _serialize(cart)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    cart = await _get_or_create_cart(db, user)
    for item in list(cart.items):
        await db.delete(item)
    await db.commit()
    return None
