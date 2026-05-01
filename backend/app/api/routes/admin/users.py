from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models import Order, User

router = APIRouter(dependencies=[Depends(require_admin)])


class AdminUserView(BaseModel):
    id: int
    email: str
    name: str
    phone: str | None = None
    is_admin: bool
    is_superadmin: bool
    created_at: datetime
    orders_count: int


class AdminUserUpdate(BaseModel):
    is_admin: bool


@router.get("", response_model=list[AdminUserView])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    orders_count = (
        select(Order.user_id, func.count(Order.id).label("c"))
        .group_by(Order.user_id)
        .subquery()
    )
    q = (
        select(User, func.coalesce(orders_count.c.c, 0).label("orders_count"))
        .outerjoin(orders_count, orders_count.c.user_id == User.id)
        .order_by(desc(User.created_at))
        .limit(limit)
    )
    if search:
        pat = f"%{search}%"
        q = q.where(or_(User.email.ilike(pat), User.name.ilike(pat)))

    rows = (await db.execute(q)).all()
    return [
        AdminUserView(
            id=u.id, email=u.email, name=u.name, phone=u.phone,
            is_admin=u.is_admin, is_superadmin=u.is_superadmin,
            created_at=u.created_at, orders_count=int(c or 0),
        )
        for u, c in rows
    ]


@router.patch("/{user_id}", response_model=AdminUserView)
async def update_user(
    user_id: int,
    body: AdminUserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_admin: Annotated[User, Depends(get_current_user)],
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Hierarchy guard: only a super-admin can modify another super-admin.
    # Without this, a regular admin promoted by the seed user could revoke
    # the seed user's privileges and lock everyone else out.
    if user.is_superadmin and not current_admin.is_superadmin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only a super-admin can modify a super-admin",
        )

    if user_id == current_admin.id and body.is_admin is False:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You cannot revoke your own admin role — ask another admin to do it",
        )

    user.is_admin = body.is_admin
    await db.commit()
    await db.refresh(user)

    count = int(
        (await db.execute(select(func.count(Order.id)).where(Order.user_id == user_id))).scalar_one()
    )
    return AdminUserView(
        id=user.id, email=user.email, name=user.name, phone=user.phone,
        is_admin=user.is_admin, is_superadmin=user.is_superadmin,
        created_at=user.created_at, orders_count=count,
    )
