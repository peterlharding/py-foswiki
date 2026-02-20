#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Security utilities
==================
- Password hashing (bcrypt direct — passlib incompatible with bcrypt>=4)
- JWT access and refresh token creation/verification
- FastAPI dependencies for extracting the current user
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt as _bcrypt_lib
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt


# -----------------------------------------------------------------------------

from .config import get_settings

# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #

def hash_password(plain: str) -> str:
    return _bcrypt_lib.hashpw(plain.encode("utf-8"), _bcrypt_lib.gensalt()).decode("utf-8")


# -----------------------------------------------------------------------------

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt_lib.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# JWT tokens
# --------------------------------------------------------------------------- #

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
_oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


# -----------------------------------------------------------------------------

def _settings():
    return get_settings()


# -----------------------------------------------------------------------------

def create_access_token(subject: str | int, extra: dict | None = None) -> str:
    s = _settings()
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=s.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, s.secret_key, algorithm=s.algorithm)


# -----------------------------------------------------------------------------

def create_refresh_token(subject: str | int) -> str:
    s = _settings()
    expire = datetime.now(tz=timezone.utc) + timedelta(days=s.refresh_token_expire_days)
    return jwt.encode(
        {"sub": str(subject), "exp": expire, "type": "refresh"},
        s.secret_key,
        algorithm=s.algorithm,
    )


# -----------------------------------------------------------------------------

def decode_token(token: str) -> dict[str, Any]:
    s = _settings()
    try:
        payload = jwt.decode(token, s.secret_key, algorithms=[s.algorithm])
        if payload.get("sub") is None:
            raise _credentials_error()
        return payload
    except JWTError:
        raise _credentials_error()


# -----------------------------------------------------------------------------

def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


# --------------------------------------------------------------------------- #
# FastAPI dependencies
# --------------------------------------------------------------------------- #

async def get_current_user_id(token: str = Depends(_oauth2_scheme)) -> str:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise _credentials_error()
    return payload["sub"]


# -----------------------------------------------------------------------------

async def get_optional_user_id(token: str | None = Depends(_oauth2_optional)) -> str | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") == "access":
            return payload["sub"]
    except HTTPException:
        pass
    return None


# -----------------------------------------------------------------------------

