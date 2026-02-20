#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
Session helpers — store/retrieve the logged-in user via a signed cookie.

We reuse the existing JWT infrastructure: the access token is stored in an
HttpOnly cookie called `access_token`.  On each request we decode it and
return the user dict, or None if missing/expired.
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Optional

from fastapi import Request, Response
from fastapi.responses import RedirectResponse

from app.core.security import decode_token
from app.core.database import get_session_factory
from app.services.users import get_user_by_id

COOKIE_NAME = "access_token"
COOKIE_MAX_AGE = 60 * 60 * 8   # 8 hours


# -----------------------------------------------------------------------------

def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=COOKIE_MAX_AGE,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


def get_token_from_request(request: Request) -> Optional[str]:
    return request.cookies.get(COOKIE_NAME)


async def get_current_user(request: Request) -> Optional[dict]:
    """
    Decode the session cookie and return the user dict, or None.
    Does NOT raise — callers decide how to handle unauthenticated requests.
    """
    token = get_token_from_request(request)
    if not token:
        return None
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        factory = get_session_factory()
        async with factory() as db:
            user = await get_user_by_id(db, user_id)
            return user.to_dict()
    except Exception:
        return None


def login_required(request: Request):
    """
    Call at the top of a route handler.  Returns a RedirectResponse to /login
    if the user is not authenticated, otherwise returns None.
    """
    token = get_token_from_request(request)
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    return None
