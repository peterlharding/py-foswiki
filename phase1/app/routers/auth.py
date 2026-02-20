#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Auth router
===========
POST /api/v1/auth/register   — create account
POST /api/v1/auth/login      — get JWT token
GET  /api/v1/auth/me         — current user info
PUT  /api/v1/auth/me         — update own profile
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_active_user,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas import TokenResponse, UserOut, UserRegister, UserUpdate

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    # Check uniqueness
    dup = await db.execute(
        select(User).where(
            (User.username == data.username) | (User.email == data.email)
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username or email already taken")

    wiki_name = _to_wiki_name(data.display_name or data.username)
    user = User(
        username=data.username,
        email=data.email,
        display_name=data.display_name or data.username,
        wiki_name=wiki_name,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserOut.from_orm(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_active_user)):
    return UserOut.from_orm(current_user)


@router.put("/me", response_model=UserOut)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if data.display_name is not None:
        current_user.display_name = data.display_name
        current_user.wiki_name = _to_wiki_name(data.display_name)
    if data.email is not None:
        # Check uniqueness
        dup = await db.execute(
            select(User).where(User.email == data.email, User.id != current_user.id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already taken")
        current_user.email = data.email
    if data.password is not None:
        current_user.hashed_password = hash_password(data.password)

    await db.flush()
    await db.refresh(current_user)
    return UserOut.from_orm(current_user)


def _to_wiki_name(name: str) -> str:
    """Convert a display name to WikiWord format: 'John Doe' → 'JohnDoe'."""
    import re
    parts = re.findall(r"[A-Za-z0-9]+", name)
    if not parts:
        return "UnknownUser"
    return "".join(p.capitalize() for p in parts)




