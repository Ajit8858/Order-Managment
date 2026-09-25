from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user, require_roles
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserOut)
async def get_my_profile(user: User = Depends(get_current_active_user)):
    return user


@router.patch("/update", response_model=UserOut)
async def update_my_profile(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.phone is not None:
        user.phone = payload.phone
    if payload.address is not None:
        user.address = payload.address
    if payload.street is not None:
        user.street = payload.street
    if payload.city is not None:
        user.city = payload.city
    if payload.state is not None:
        user.state = payload.state
    if payload.zip_code is not None:
        user.zip_code = payload.zip_code
    await db.commit()
    await db.refresh(user)
    return user


@router.get("", response_model=list[UserOut], dependencies=[Depends(require_roles(UserRole.ADMIN))])
async def list_users(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()
