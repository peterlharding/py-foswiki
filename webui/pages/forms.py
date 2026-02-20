#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
DataForms web UI pages.

Admin:
  GET  /forms                         List all form schemas
  GET  /forms/new                     Create schema
  POST /forms/new
  GET  /forms/{schema_id}/edit        Edit schema + fields
  POST /forms/{schema_id}/edit
  POST /forms/{schema_id}/delete

Topic form assignment (any logged-in user with edit rights):
  GET  /webs/{web}/topics/{topic}/form        Assign/change form
  POST /webs/{web}/topics/{topic}/form
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas import FormSchemaCreate, FormSchemaUpdate, FormFieldCreate
from app.services import forms as form_svc
from app.services.topics import get_topic
from app.services.webs import list_webs
from webui.context import PageContext
from webui.session import get_current_user
from webui.templating import templates

router = APIRouter(tags=["webui-forms"])


# ── helpers ───────────────────────────────────────────────────────────────────

async def _require_admin(request: Request):
    user = await get_current_user(request)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    if not user.get("is_admin"):
        ctx = PageContext(title="Forbidden", user=user)
        return None, templates.TemplateResponse("error.html", {
            **ctx.to_dict(request), "message": "Admin access required.",
        }, status_code=403)
    return user, None


async def _require_login(request: Request):
    user = await get_current_user(request)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    return user, None


def _parse_fields_from_form(form_data: dict) -> list[FormFieldCreate]:
    """
    Parse repeated field rows from a POST form.
    Expects keys like: field_name_0, field_label_0, field_type_0, ...
    """
    fields = []
    i = 0
    while f"field_name_{i}" in form_data:
        name = form_data.get(f"field_name_{i}", "").strip()
        if name:
            fields.append(FormFieldCreate(
                name=name,
                label=form_data.get(f"field_label_{i}", name),
                field_type=form_data.get(f"field_type_{i}", "text"),
                options=form_data.get(f"field_options_{i}", ""),
                default_value=form_data.get(f"field_default_{i}", ""),
                is_required=bool(form_data.get(f"field_required_{i}", "")),
                position=i,
            ))
        i += 1
    return fields


# ── Schema list ───────────────────────────────────────────────────────────────

@router.get("/forms", response_class=HTMLResponse)
async def forms_list(request: Request, db: AsyncSession = Depends(get_db)):
    user, err = await _require_admin(request)
    if err:
        return err
    schemas = await form_svc.list_schemas(db)
    ctx = PageContext(title="Form Schemas", user=user)
    return templates.TemplateResponse("forms/list.html", {
        **ctx.to_dict(request),
        "schemas": schemas,
    })


# ── Create schema ─────────────────────────────────────────────────────────────

@router.get("/forms/new", response_class=HTMLResponse)
async def new_schema_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, err = await _require_admin(request)
    if err:
        return err
    webs = await list_webs(db)
    ctx = PageContext(title="New Form Schema", user=user)
    return templates.TemplateResponse("forms/edit.html", {
        **ctx.to_dict(request),
        "schema": None,
        "webs": webs,
        "error": "",
    })


@router.post("/forms/new")
async def new_schema_submit(request: Request, db: AsyncSession = Depends(get_db)):
    user, err = await _require_admin(request)
    if err:
        return err
    form_data = dict(await request.form())
    try:
        fields = _parse_fields_from_form(form_data)
        data = FormSchemaCreate(
            name=form_data.get("name", ""),
            description=form_data.get("description", ""),
            web_name=form_data.get("web_name") or None,
            fields=fields,
        )
        schema = await form_svc.create_schema(db, data)
        return RedirectResponse(url=f"/forms/{schema.id}/edit", status_code=302)
    except Exception as e:
        webs = await list_webs(db)
        ctx = PageContext(title="New Form Schema", user=user)
        return templates.TemplateResponse("forms/edit.html", {
            **ctx.to_dict(request),
            "schema": None,
            "webs": webs,
            "error": str(e),
        }, status_code=400)


# ── Edit schema ───────────────────────────────────────────────────────────────

@router.get("/forms/{schema_id}/edit", response_class=HTMLResponse)
async def edit_schema_page(
    schema_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    user, err = await _require_admin(request)
    if err:
        return err
    schema = await form_svc.get_schema_by_id(db, schema_id)
    webs = await list_webs(db)
    ctx = PageContext(title=f"Edit {schema.name}", user=user)
    return templates.TemplateResponse("forms/edit.html", {
        **ctx.to_dict(request),
        "schema": schema,
        "webs": webs,
        "error": "",
        "success": "",
    })


@router.post("/forms/{schema_id}/edit")
async def edit_schema_submit(
    schema_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    user, err = await _require_admin(request)
    if err:
        return err
    form_data = dict(await request.form())
    schema = await form_svc.get_schema_by_id(db, schema_id)
    webs = await list_webs(db)
    try:
        fields = _parse_fields_from_form(form_data)
        data = FormSchemaUpdate(
            description=form_data.get("description", ""),
            fields=fields,
        )
        schema = await form_svc.update_schema(db, schema_id, data)
        ctx = PageContext(title=f"Edit {schema.name}", user=user)
        return templates.TemplateResponse("forms/edit.html", {
            **ctx.to_dict(request),
            "schema": schema,
            "webs": webs,
            "error": "",
            "success": "Schema saved.",
        })
    except Exception as e:
        ctx = PageContext(title=f"Edit {schema.name}", user=user)
        return templates.TemplateResponse("forms/edit.html", {
            **ctx.to_dict(request),
            "schema": schema,
            "webs": webs,
            "error": str(e),
            "success": "",
        }, status_code=400)


# ── Delete schema ─────────────────────────────────────────────────────────────

@router.post("/forms/{schema_id}/delete")
async def delete_schema(
    schema_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    user, err = await _require_admin(request)
    if err:
        return err
    await form_svc.delete_schema(db, schema_id)
    return RedirectResponse(url="/forms", status_code=302)


# ── Topic form assignment ─────────────────────────────────────────────────────

@router.get("/webs/{web_name}/topics/{topic_name}/form", response_class=HTMLResponse)
async def topic_form_page(
    web_name: str, topic_name: str,
    request: Request, db: AsyncSession = Depends(get_db),
):
    user, err = await _require_login(request)
    if err:
        return err
    topic, ver = await get_topic(db, web_name, topic_name)
    schemas = await form_svc.list_schemas(db, web_name=web_name)
    values = await form_svc.get_field_values(db, topic.id)
    ctx = PageContext(title=f"Form — {web_name}.{topic_name}", user=user,
                      web=web_name, topic=topic_name)
    return templates.TemplateResponse("forms/topic_form.html", {
        **ctx.to_dict(request),
        "web": web_name,
        "topic": topic,
        "schemas": schemas,
        "current_schema": topic.form_schema,
        "values": values,
        "error": "",
        "success": "",
    })


@router.post("/webs/{web_name}/topics/{topic_name}/form")
async def topic_form_submit(
    web_name: str, topic_name: str,
    request: Request, db: AsyncSession = Depends(get_db),
):
    user, err = await _require_login(request)
    if err:
        return err
    topic, ver = await get_topic(db, web_name, topic_name)
    form_data = dict(await request.form())
    schema_id = form_data.get("schema_id") or None

    try:
        await form_svc.assign_form(db, topic, schema_id)
        if schema_id:
            schema = await form_svc.get_schema_by_id(db, schema_id)
            field_values = {
                f.name: form_data.get(f"field_{f.name}", f.default_value)
                for f in schema.fields
            }
            missing = [
                f.label for f in schema.fields
                if f.is_required and not field_values.get(f.name, "").strip()
            ]
            if missing:
                raise ValueError(f"Required fields missing: {', '.join(missing)}")
            await form_svc.set_field_values(db, topic.id, field_values)
        return RedirectResponse(
            url=f"/webs/{web_name}/topics/{topic_name}", status_code=302
        )
    except Exception as e:
        schemas = await form_svc.list_schemas(db, web_name=web_name)
        values = await form_svc.get_field_values(db, topic.id)
        ctx = PageContext(title=f"Form — {web_name}.{topic_name}", user=user,
                          web=web_name, topic=topic_name)
        return templates.TemplateResponse("forms/topic_form.html", {
            **ctx.to_dict(request),
            "web": web_name,
            "topic": topic,
            "schemas": schemas,
            "current_schema": topic.form_schema,
            "values": values,
            "error": str(e),
            "success": "",
        }, status_code=400)
