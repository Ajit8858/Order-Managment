import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_active_user
from app.database import get_db
from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentOut
from app.services.order_state import assert_valid_transition
from app.tasks.email_tasks import send_order_confirmation_email, send_payment_failed_email
from app.tasks.invoice_tasks import generate_invoice

router = APIRouter(prefix="/payments", tags=["Payments"])

MAX_RETRIES = 3


def _simulate_gateway(card_token: str) -> tuple[bool, str | None]:
    """Deterministic simulated payment gateway (no real PSP involved).

    A token ending in 'fail' always fails, so tests/demos are deterministic;
    everything else succeeds. Swap this for a real Stripe/PSP call later —
    the rest of the flow (state machine, tasks, retries) doesn't need to change.
    """
    if card_token.endswith("fail"):
        return False, "card_declined"
    return True, None


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def process_payment(
    payload: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    stmt = select(Order).where(Order.id == payload.order_id).options(
        selectinload(Order.items).selectinload(OrderItem.product),
        selectinload(Order.payment),
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")
    if order.status not in (OrderStatus.PENDING, OrderStatus.PAYMENT_FAILED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Order is already {order.status.value}")

    payment = order.payment
    if payment and payment.retry_count >= MAX_RETRIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum payment retries exceeded")

    success, reason = _simulate_gateway(payload.card_token)

    if payment is None:
        payment = Payment(
            order_id=order.id,
            amount=order.total_amount,
            transaction_ref=f"txn_{uuid.uuid4().hex[:16]}",
        )
        db.add(payment)

    if success:
        payment.status = PaymentStatus.SUCCESS
        payment.failure_reason = None

        assert_valid_transition(order.status, OrderStatus.PAYMENT_SUCCESS)
        order.status = OrderStatus.PAYMENT_SUCCESS
        await db.flush()
        # Successful payment auto-confirms the order — no manual step needed.
        assert_valid_transition(order.status, OrderStatus.ORDER_CONFIRMED)
        order.status = OrderStatus.ORDER_CONFIRMED

        await db.commit()

        send_order_confirmation_email.delay(user.email, str(order.id), str(order.total_amount))
        generate_invoice.delay(str(order.id))
    else:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = reason
        payment.retry_count = (payment.retry_count or 0) + 1

        assert_valid_transition(order.status, OrderStatus.PAYMENT_FAILED)
        order.status = OrderStatus.PAYMENT_FAILED

        await db.commit()
        send_payment_failed_email.delay(user.email, str(order.id), reason or "unknown")

    await db.refresh(payment)
    return payment


@router.get("/{order_id}", response_model=PaymentOut)
async def get_payment(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_active_user)):
    stmt = select(Payment).join(Order).where(Payment.order_id == order_id)
    payment = (await db.execute(stmt)).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    order = await db.get(Order, order_id)
    if order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")
    return payment
