#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Auth router
===========
POST /api/v1/auth/register  — create account
POST /api/v1/auth/token     — login (OAuth2 form)
POST /api/v1/auth/refresh   — exchange refresh token for new access token
GET  /api/v1/auth/me        — current user info
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

from app.core.security import (
    create_access_token, create_refresh_token,
    decode_token, get_current_user_id,
)

from app.schemas import RefreshRequest, TokenResponse, UserCreate, UserResponse
from app.services.users import authenticate_user, create_user, get_user_by_id, set_admin

# -----------------------------------------------------------------------------

router = APIRouter(prefix="/auth", tags=["auth"])


# -----------------------------------------------------------------------------

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await create_user(db, data)
    return _user_response(user)


# -----------------------------------------------------------------------------

@router.post("/token", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, form.username, form.password)
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, extra={"username": user.username}),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


# -----------------------------------------------------------------------------

@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await get_user_by_id(db, payload["sub"])
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, extra={"username": user.username}),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


# -----------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    return _user_response(user)


# -----------------------------------------------------------------------------

@router.patch("/users/{username}/make-admin", response_model=UserResponse)
async def make_admin(
    username: str,
    caller_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    caller = await get_user_by_id(db, caller_id)
    if not caller.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    user = await set_admin(db, username, is_admin=True)
    return _user_response(user)


@router.patch("/users/{username}/revoke-admin", response_model=UserResponse)
async def revoke_admin(
    username: str,
    caller_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    caller = await get_user_by_id(db, caller_id)
    if not caller.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    user = await set_admin(db, username, is_admin=False)
    return _user_response(user)


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────

def _user_response(user) -> dict:
    return {
        "id":           user.id,
        "username":     user.username,
        "email":        user.email,
        "display_name": user.display_name,
        "wiki_name":    user.wiki_name,
        "is_admin":     user.is_admin,
        "groups":       user.groups_list(),
        "created_at":   user.created_at,
    }


# -----------------------------------------------------------------------------

