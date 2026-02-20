#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
User management pages.

Admin-only:
  GET  /users                       — list all users
  GET  /users/{username}            — user detail
  GET  /users/{username}/edit       — edit profile (admin can edit anyone)
  POST /users/{username}/edit
  POST /users/{username}/toggle-admin
  POST /users/{username}/toggle-active
  POST /users/{username}/delete

Self-service (any logged-in user):
  GET  /profile                     — edit own display name / email
  POST /profile
  GET  /profile/password            — change own password
  POST /profile/password
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas import UserUpdate
from app.services.users import (
    change_password,
    delete_user,
    get_user_by_username,
    list_users,
    set_active,
    set_admin,
    update_user,
)
from webui.context import PageContext
from webui.session import get_current_user
from webui.templating import templates

router = APIRouter(tags=["webui-users"])


# ── helpers ───────────────────────────────────────────────────────────────────

async def _require_user(request: Request):
    user = await get_current_user(request)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    return user, None


async def _require_admin(request: Request):
    user, redir = await _require_user(request)
    if redir:
        return None, redir
    if not user.get("is_admin"):
        ctx = PageContext(title="Forbidden", user=user)
        return None, templates.TemplateResponse("error.html", {
            **ctx.to_dict(request),
            "message": "Admin access required.",
        }, status_code=403)
    return user, None


# ── Admin: user list ──────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def user_list(request: Request, db: AsyncSession = Depends(get_db)):
    user, err = await _require_admin(request)
    if err:
        return err
    users = await list_users(db, limit=200)
    ctx = PageContext(title="Users", user=user)
    return templates.TemplateResponse("users/list.html", {
        **ctx.to_dict(request),
        "users": users,
    })


# ── Admin: edit any user ──────────────────────────────────────────────────────

@router.get("/users/{username}/edit", response_class=HTMLResponse)
async def edit_user_page(username: str, request: Request, db: AsyncSession = Depends(get_db)):
    user, err = await _require_admin(request)
    if err:
        return err
    target = await get_user_by_username(db, username)
    if not target:
        ctx = PageContext(title="Not Found", user=user)
        return templates.TemplateResponse("error.html", {
            **ctx.to_dict(request), "message": f"User '{username}' not found."
        }, status_code=404)
    ctx = PageContext(title=f"Edit {username}", user=user)
    return templates.TemplateResponse("users/edit.html", {
        **ctx.to_dict(request),
        "target": target,
        "error": "",
        "success": "",
    })


@router.post("/users/{username}/edit")
async def edit_user_submit(
    username: str,
    request: Request,
    email: str = Form(...),
    display_name: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    user, err = await _require_admin(request)
    if err:
        return err
    target = await get_user_by_username(db, username)
    if not target:
        return RedirectResponse(url="/users", status_code=302)
    try:
        await update_user(db, target.id, UserUpdate(email=email, display_name=display_name))
        ctx = PageContext(title=f"Edit {username}", user=user)
        target = await get_user_by_username(db, username)
        return templates.TemplateResponse("users/edit.html", {
            **ctx.to_dict(request),
            "target": target,
            "error": "",
            "success": "Profile updated.",
        })
    except Exception as e:
        ctx = PageContext(title=f"Edit {username}", user=user)
        return templates.TemplateResponse("users/edit.html", {
            **ctx.to_dict(request),
            "target": target,
            "error": str(e),
            "success": "",
        }, status_code=400)


# ── Admin: toggle admin / active / delete ─────────────────────────────────────

@router.post("/users/{username}/toggle-admin")
async def toggle_admin(username: str, request: Request, db: AsyncSession = Depends(get_db)):
    user, err = await _require_admin(request)
    if err:
        return err
    target = await get_user_by_username(db, username)
    if target:
        await set_admin(db, username, not target.is_admin)
    return RedirectResponse(url="/users", status_code=302)


@router.post("/users/{username}/toggle-active")
async def toggle_active(username: str, request: Request, db: AsyncSession = Depends(get_db)):
    user, err = await _require_admin(request)
    if err:
        return err
    target = await get_user_by_username(db, username)
    if target:
        await set_active(db, username, not target.is_active)
    return RedirectResponse(url="/users", status_code=302)


@router.post("/users/{username}/delete")
async def delete_user_submit(username: str, request: Request, db: AsyncSession = Depends(get_db)):
    user, err = await _require_admin(request)
    if err:
        return err
    if username == user.get("username"):
        return RedirectResponse(url="/users", status_code=302)
    await delete_user(db, username)
    return RedirectResponse(url="/users", status_code=302)


# ── Admin: reset another user's password ─────────────────────────────────────

@router.get("/users/{username}/reset-password", response_class=HTMLResponse)
async def reset_password_page(username: str, request: Request, db: AsyncSession = Depends(get_db)):
    user, err = await _require_admin(request)
    if err:
        return err
    target = await get_user_by_username(db, username)
    if not target:
        return RedirectResponse(url="/users", status_code=302)
    ctx = PageContext(title=f"Reset password — {username}", user=user)
    return templates.TemplateResponse("users/reset_password.html", {
        **ctx.to_dict(request),
        "target": target,
        "error": "",
        "success": "",
    })


@router.post("/users/{username}/reset-password")
async def reset_password_submit(
    username: str,
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user, err = await _require_admin(request)
    if err:
        return err
    target = await get_user_by_username(db, username)
    if not target:
        return RedirectResponse(url="/users", status_code=302)

    from app.core.security import hash_password
    ctx = PageContext(title=f"Reset password — {username}", user=user)

    if new_password != confirm_password:
        return templates.TemplateResponse("users/reset_password.html", {
            **ctx.to_dict(request),
            "target": target,
            "error": "Passwords do not match.",
            "success": "",
        }, status_code=400)
    if len(new_password) < 8:
        return templates.TemplateResponse("users/reset_password.html", {
            **ctx.to_dict(request),
            "target": target,
            "error": "Password must be at least 8 characters.",
            "success": "",
        }, status_code=400)

    target.password_hash = hash_password(new_password)
    await db.flush()
    return templates.TemplateResponse("users/reset_password.html", {
        **ctx.to_dict(request),
        "target": target,
        "error": "",
        "success": f"Password for {username} has been reset.",
    })


# ── Self-service: edit own profile ────────────────────────────────────────────

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, redir = await _require_user(request)
    if redir:
        return redir
    target = await get_user_by_username(db, user["username"])
    ctx = PageContext(title="My Profile", user=user)
    return templates.TemplateResponse("users/profile.html", {
        **ctx.to_dict(request),
        "target": target,
        "error": "",
        "success": "",
    })


@router.post("/profile")
async def profile_submit(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    user, redir = await _require_user(request)
    if redir:
        return redir
    target = await get_user_by_username(db, user["username"])
    ctx = PageContext(title="My Profile", user=user)
    try:
        await update_user(db, target.id, UserUpdate(email=email, display_name=display_name))
        target = await get_user_by_username(db, user["username"])
        return templates.TemplateResponse("users/profile.html", {
            **ctx.to_dict(request),
            "target": target,
            "error": "",
            "success": "Profile updated.",
        })
    except Exception as e:
        return templates.TemplateResponse("users/profile.html", {
            **ctx.to_dict(request),
            "target": target,
            "error": str(e),
            "success": "",
        }, status_code=400)


# ── Self-service: change own password ─────────────────────────────────────────

@router.get("/profile/password", response_class=HTMLResponse)
async def change_password_page(request: Request):
    user, redir = await _require_user(request)
    if redir:
        return redir
    ctx = PageContext(title="Change Password", user=user)
    return templates.TemplateResponse("users/change_password.html", {
        **ctx.to_dict(request),
        "error": "",
        "success": "",
    })


@router.post("/profile/password")
async def change_password_submit(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user, redir = await _require_user(request)
    if redir:
        return redir
    ctx = PageContext(title="Change Password", user=user)
    if new_password != confirm_password:
        return templates.TemplateResponse("users/change_password.html", {
            **ctx.to_dict(request),
            "error": "New passwords do not match.",
            "success": "",
        }, status_code=400)
    if len(new_password) < 8:
        return templates.TemplateResponse("users/change_password.html", {
            **ctx.to_dict(request),
            "error": "Password must be at least 8 characters.",
            "success": "",
        }, status_code=400)
    try:
        await change_password(db, user["id"], old_password, new_password)
        return templates.TemplateResponse("users/change_password.html", {
            **ctx.to_dict(request),
            "error": "",
            "success": "Password changed successfully.",
        })
    except Exception as e:
        return templates.TemplateResponse("users/change_password.html", {
            **ctx.to_dict(request),
            "error": str(e),
            "success": "",
        }, status_code=400)
