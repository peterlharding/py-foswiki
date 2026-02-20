#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
Group management web UI pages.

GET  /groups                        — list all groups (alpha index)
GET  /groups/new                    — create group form
POST /groups/new                    — create group (add first member or just name)
GET  /groups/{name}                 — view/edit group members
POST /groups/{name}/add             — add a member
POST /groups/{name}/remove          — remove a member
POST /groups/{name}/rename          — rename the group
POST /groups/{name}/delete          — delete the group
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import groups as grp_svc
from webui.context import PageContext
from webui.session import get_current_user
from webui.templating import templates

router = APIRouter(tags=["webui-groups"])


# ── helpers ───────────────────────────────────────────────────────────────────

async def _require_admin(request, user):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        return None  # caller renders 403


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/groups", response_class=HTMLResponse)
async def groups_list(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        ctx = PageContext(title="Forbidden", user=user)
        return templates.TemplateResponse("error.html", {
            **ctx.to_dict(request), "message": "Admin access required.",
        }, status_code=403)

    groups = await grp_svc.list_groups(db)

    # Build alpha index — letters that have at least one group
    letters = sorted({name[0].upper() for name in groups} if groups else set())

    # Group by first letter
    by_letter: dict[str, list[tuple[str, int]]] = {}
    for name, members in groups.items():
        letter = name[0].upper()
        by_letter.setdefault(letter, []).append((name, len(members)))

    ctx = PageContext(title="WikiGroups", user=user)
    return templates.TemplateResponse("groups/list.html", {
        **ctx.to_dict(request),
        "by_letter": by_letter,
        "letters": letters,
        "total": len(groups),
    })


# ── New group ─────────────────────────────────────────────────────────────────

@router.get("/groups/new", response_class=HTMLResponse)
async def new_group_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        ctx = PageContext(title="Forbidden", user=user)
        return templates.TemplateResponse("error.html", {
            **ctx.to_dict(request), "message": "Admin access required.",
        }, status_code=403)

    all_users = await grp_svc.get_all_users(db)
    ctx = PageContext(title="New Group", user=user)
    return templates.TemplateResponse("groups/edit.html", {
        **ctx.to_dict(request),
        "group_name": "",
        "members": [],
        "all_users": all_users,
        "is_new": True,
        "error": "",
    })


@router.post("/groups/new")
async def new_group_submit(
    request: Request,
    group_name: str = Form(...),
    initial_members: list[str] = Form(default=[]),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        return RedirectResponse(url="/groups", status_code=302)

    group_name = group_name.strip()
    if not group_name:
        all_users = await grp_svc.get_all_users(db)
        ctx = PageContext(title="New Group", user=user)
        return templates.TemplateResponse("groups/edit.html", {
            **ctx.to_dict(request),
            "group_name": "",
            "members": [],
            "all_users": all_users,
            "is_new": True,
            "error": "Group name is required.",
        }, status_code=400)

    # Check for duplicate
    existing = await grp_svc.list_groups(db)
    if group_name in existing:
        all_users = await grp_svc.get_all_users(db)
        ctx = PageContext(title="New Group", user=user)
        return templates.TemplateResponse("groups/edit.html", {
            **ctx.to_dict(request),
            "group_name": group_name,
            "members": [],
            "all_users": all_users,
            "is_new": True,
            "error": f"Group '{group_name}' already exists.",
        }, status_code=400)

    for username in initial_members:
        await grp_svc.add_member(db, group_name, username)

    return RedirectResponse(url=f"/groups/{group_name}", status_code=302)


# ── Edit group ────────────────────────────────────────────────────────────────

@router.get("/groups/{group_name}", response_class=HTMLResponse)
async def edit_group_page(
    group_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        ctx = PageContext(title="Forbidden", user=user)
        return templates.TemplateResponse("error.html", {
            **ctx.to_dict(request), "message": "Admin access required.",
        }, status_code=403)

    members = await grp_svc.get_group_members(db, group_name)
    all_users = await grp_svc.get_all_users(db)
    member_names = {u.username for u in members}

    ctx = PageContext(title=f"Group: {group_name}", user=user)
    return templates.TemplateResponse("groups/edit.html", {
        **ctx.to_dict(request),
        "group_name": group_name,
        "members": members,
        "member_names": member_names,
        "all_users": all_users,
        "is_new": False,
        "error": "",
    })


# ── Add member ────────────────────────────────────────────────────────────────

@router.post("/groups/{group_name}/add")
async def add_member(
    group_name: str,
    request: Request,
    username: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        return RedirectResponse(url="/groups", status_code=302)
    await grp_svc.add_member(db, group_name, username)
    return RedirectResponse(url=f"/groups/{group_name}", status_code=302)


# ── Remove member ─────────────────────────────────────────────────────────────

@router.post("/groups/{group_name}/remove")
async def remove_member(
    group_name: str,
    request: Request,
    username: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        return RedirectResponse(url="/groups", status_code=302)
    await grp_svc.remove_member(db, group_name, username)
    return RedirectResponse(url=f"/groups/{group_name}", status_code=302)


# ── Rename group ──────────────────────────────────────────────────────────────

@router.post("/groups/{group_name}/rename")
async def rename_group(
    group_name: str,
    request: Request,
    new_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        return RedirectResponse(url="/groups", status_code=302)
    new_name = new_name.strip()
    if new_name and new_name != group_name:
        await grp_svc.rename_group(db, group_name, new_name)
        return RedirectResponse(url=f"/groups/{new_name}", status_code=302)
    return RedirectResponse(url=f"/groups/{group_name}", status_code=302)


# ── Delete group ──────────────────────────────────────────────────────────────

@router.post("/groups/{group_name}/delete")
async def delete_group(
    group_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        return RedirectResponse(url="/groups", status_code=302)
    await grp_svc.delete_group(db, group_name)
    return RedirectResponse(url="/groups", status_code=302)
