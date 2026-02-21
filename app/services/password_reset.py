#!/usr/bin/env python
# -----------------------------------------------------------------------------
"""
Password reset service
======================
Generates single-use tokens, validates them, and applies new passwords.
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import PasswordResetToken, User


# Token lifetime
TOKEN_EXPIRE_HOURS = 1


# -----------------------------------------------------------------------------

async def create_reset_token(db: AsyncSession, email: str) -> tuple[User, str] | None:
    """
    Look up a user by email and create a reset token.
    Returns (user, raw_token) or None if no user with that email exists.
    Does NOT raise — callers should not reveal whether the email exists.
    """
    result = await db.execute(select(User).where(User.email == email, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        return None

    # Invalidate any existing tokens for this user
    await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )

    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)

    token_obj = PasswordResetToken(
        user_id=user.id,
        token=raw_token,
        expires_at=expires_at,
    )
    db.add(token_obj)
    await db.flush()

    return user, raw_token


# -----------------------------------------------------------------------------

async def validate_reset_token(db: AsyncSession, raw_token: str) -> User:
    """
    Validate a reset token and return the associated User.
    Raises HTTP 400 if the token is invalid or expired.
    """
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == raw_token)
    )
    token_obj = result.scalar_one_or_none()

    if not token_obj:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    expires = token_obj.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(tz=timezone.utc) > expires:
        await db.delete(token_obj)
        await db.flush()
        raise HTTPException(status_code=400, detail="This reset link has expired. Please request a new one.")

    user = await db.get(User, token_obj.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    return user


# -----------------------------------------------------------------------------

async def apply_reset_token(db: AsyncSession, raw_token: str, new_password: str) -> User:
    """
    Validate token, set the new password, delete the token, return the user.
    Raises HTTP 400 on invalid/expired token.
    """
    user = await validate_reset_token(db, raw_token)

    user.password_hash = hash_password(new_password)

    # Delete the used token
    await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    await db.flush()

    return user
