#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
DataForms API routes.

GET    /api/v1/forms                    List all schemas (optional ?web=)
POST   /api/v1/forms                    Create schema
GET    /api/v1/forms/{schema_id}        Get schema
PUT    /api/v1/forms/{schema_id}        Update schema
DELETE /api/v1/forms/{schema_id}        Delete schema

GET    /api/v1/webs/{web}/topics/{topic}/form        Get assigned form + values
PUT    /api/v1/webs/{web}/topics/{topic}/form        Assign form + set values
DELETE /api/v1/webs/{web}/topics/{topic}/form        Remove form from topic
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models import FormSchema, Topic
from app.schemas import (
    FormSchemaCreate, FormSchemaResponse, FormSchemaUpdate, OKResponse
)
from app.services import forms as form_svc
from app.services.webs import get_web_by_name
from app.services.topics import _get_topic

router = APIRouter(tags=["forms"])


# ── Schema CRUD ───────────────────────────────────────────────────────────────

@router.get("/forms", response_model=list[FormSchemaResponse])
async def list_schemas(
    web: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user_id),
):
    schemas = await form_svc.list_schemas(db, web_name=web)
    return [_schema_response(s) for s in schemas]


@router.post("/forms", response_model=FormSchemaResponse, status_code=201)
async def create_schema(
    data: FormSchemaCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user_id),
):
    schema = await form_svc.create_schema(db, data)
    return _schema_response(schema)


@router.get("/forms/{schema_id}", response_model=FormSchemaResponse)
async def get_schema(
    schema_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user_id),
):
    schema = await form_svc.get_schema_by_id(db, schema_id)
    return _schema_response(schema)


@router.put("/forms/{schema_id}", response_model=FormSchemaResponse)
async def update_schema(
    schema_id: str,
    data: FormSchemaUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user_id),
):
    schema = await form_svc.update_schema(db, schema_id, data)
    return _schema_response(schema)


@router.delete("/forms/{schema_id}", response_model=OKResponse)
async def delete_schema(
    schema_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user_id),
):
    await form_svc.delete_schema(db, schema_id)
    return OKResponse(message="Schema deleted")


# ── Per-topic form endpoints ──────────────────────────────────────────────────

@router.get("/webs/{web_name}/topics/{topic_name}/form")
async def get_topic_form(
    web_name: str,
    topic_name: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user_id),
):
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web.id, topic_name)
    if not topic.form_schema_id:
        return {"schema": None, "values": {}}
    schema = await form_svc.get_schema_by_id(db, topic.form_schema_id)
    values = await form_svc.get_field_values(db, topic.id)
    return {"schema": _schema_response(schema), "values": values}


@router.put("/webs/{web_name}/topics/{topic_name}/form")
async def set_topic_form(
    web_name: str,
    topic_name: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user_id),
):
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web.id, topic_name)
    schema_id = body.get("schema_id")
    values = body.get("values", {})
    await form_svc.assign_form(db, topic, schema_id)
    if values:
        await form_svc.set_field_values(db, topic.id, values)
    return {"ok": True}


@router.delete("/webs/{web_name}/topics/{topic_name}/form", response_model=OKResponse)
async def remove_topic_form(
    web_name: str,
    topic_name: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user_id),
):
    web = await get_web_by_name(db, web_name)
    topic = await _get_topic(db, web.id, topic_name)
    await form_svc.assign_form(db, topic, None)
    return OKResponse(message="Form removed from topic")


# ── helpers ───────────────────────────────────────────────────────────────────

def _schema_response(schema: FormSchema) -> dict:
    return {
        "id":          schema.id,
        "name":        schema.name,
        "description": schema.description,
        "web_id":      schema.web_id,
        "web_name":    schema.web.name if schema.web else None,
        "fields": [
            {
                "id":            f.id,
                "schema_id":     f.schema_id,
                "name":          f.name,
                "label":         f.label,
                "field_type":    f.field_type,
                "options":       f.options,
                "default_value": f.default_value,
                "is_required":   f.is_required,
                "position":      f.position,
            }
            for f in sorted(schema.fields, key=lambda x: x.position)
        ],
        "created_at":  schema.created_at,
        "updated_at":  schema.updated_at,
    }
