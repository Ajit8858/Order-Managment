from fastapi import HTTPException, status

from app.models.order import OrderStatus, ALLOWED_TRANSITIONS


def assert_valid_transition(current: OrderStatus, target: OrderStatus) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition order from {current.value} to {target.value}",
        )
