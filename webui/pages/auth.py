#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""Auth pages: login, register, logout."""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.services.users import authenticate_user, create_user, set_admin
from app.schemas import UserCreate
from webui.context import PageContext
from webui.session import clear_session_cookie, get_current_user, set_session_cookie
from webui.templating import templates

router = APIRouter(tags=["webui-auth"])


# -----------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    ctx = PageContext(title="Login")
    return templates.TemplateResponse("auth/login.html", {
        **ctx.to_dict(request),
        "error": error,
    })


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await authenticate_user(db, username, password)
        token = create_access_token(user.id, extra={"username": user.username})
        response = RedirectResponse(url="/", status_code=302)
        set_session_cookie(response, token)
        return response
    except Exception:
        ctx = PageContext(title="Login")
        return templates.TemplateResponse("auth/login.html", {
            **ctx.to_dict(request),
            "error": "Invalid username or password",
        }, status_code=401)


# -----------------------------------------------------------------------------

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    caller = await get_current_user(request)
    if not get_settings().allow_registration and not (caller and caller.get("is_admin")):
        ctx = PageContext(title="Registration Disabled", user=caller)
        return templates.TemplateResponse("auth/registration_closed.html", {
            **ctx.to_dict(request),
        }, status_code=403)
    ctx = PageContext(title="Register", user=caller)
    return templates.TemplateResponse("auth/register.html", {
        **ctx.to_dict(request),
        "error": "",
    })


@router.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(default=""),
    make_admin: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    caller = await get_current_user(request)
    caller_is_admin = caller and caller.get("is_admin")
    if not get_settings().allow_registration and not caller_is_admin:
        return RedirectResponse(url="/login", status_code=302)
    try:
        data = UserCreate(
            username=username,
            email=email,
            password=password,
            display_name=display_name,
        )
        new_user = await create_user(db, data)
        if caller_is_admin and make_admin:
            await set_admin(db, username, is_admin=True)
        if caller_is_admin:
            return RedirectResponse(url="/users", status_code=302)
        token = create_access_token(new_user.id, extra={"username": new_user.username})
        response = RedirectResponse(url="/", status_code=302)
        set_session_cookie(response, token)
        return response
    except Exception as e:
        ctx = PageContext(title="Register", user=caller)
        return templates.TemplateResponse("auth/register.html", {
            **ctx.to_dict(request),
            "error": str(e),
        }, status_code=400)


# -----------------------------------------------------------------------------

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    clear_session_cookie(response)
    return response
