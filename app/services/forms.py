#!/usr/bin/env python3
# -----------------------------------------------------------------------------
"""
DataForms service — CRUD for form schemas, fields, and topic field values.
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FormField, FormSchema, Topic, TopicMeta
from app.schemas import FormSchemaCreate, FormSchemaUpdate
from app.services.webs import get_web_by_name


# ── Schema CRUD ───────────────────────────────────────────────────────────────

async def list_schemas(
    db: AsyncSession,
    web_name: Optional[str] = None,
) -> list[FormSchema]:
    """Return all schemas visible for a web (web-scoped + global)."""
    stmt = (
        select(FormSchema)
        .options(selectinload(FormSchema.fields))
        .order_by(FormSchema.name)
    )
    if web_name:
        web = await get_web_by_name(db, web_name)
        stmt = stmt.where(
            (FormSchema.web_id == web.id) | (FormSchema.web_id.is_(None))
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# -----------------------------------------------------------------------------

async def get_schema_by_id(db: AsyncSession, schema_id: str) -> FormSchema:
    result = await db.execute(
        select(FormSchema)
        .options(selectinload(FormSchema.fields))
        .where(FormSchema.id == schema_id)
    )
    schema = result.scalar_one_or_none()
    if not schema:
        raise HTTPException(status_code=404, detail="Form schema not found")
    return schema


# -----------------------------------------------------------------------------

async def get_schema_by_name(
    db: AsyncSession, name: str, web_name: Optional[str] = None
) -> Optional[FormSchema]:
    stmt = (
        select(FormSchema)
        .options(selectinload(FormSchema.fields))
        .where(FormSchema.name == name)
    )
    if web_name:
        web = await get_web_by_name(db, web_name)
        stmt = stmt.where(
            (FormSchema.web_id == web.id) | (FormSchema.web_id.is_(None))
        )
    result = await db.execute(stmt)
    return result.scalars().first()


# -----------------------------------------------------------------------------

async def create_schema(db: AsyncSession, data: FormSchemaCreate) -> FormSchema:
    web_id = None
    if data.web_name:
        web = await get_web_by_name(db, data.web_name)
        web_id = web.id

    existing = await db.execute(
        select(FormSchema).where(
            FormSchema.name == data.name,
            FormSchema.web_id == web_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Form schema '{data.name}' already exists",
        )

    schema = FormSchema(name=data.name, description=data.description, web_id=web_id)
    db.add(schema)
    await db.flush()

    for i, f in enumerate(data.fields):
        db.add(FormField(
            schema_id=schema.id,
            name=f.name,
            label=f.label,
            field_type=f.field_type,
            options=f.options,
            default_value=f.default_value,
            is_required=f.is_required,
            position=f.position if f.position else i,
        ))
    await db.flush()

    return await get_schema_by_id(db, schema.id)


# -----------------------------------------------------------------------------

async def update_schema(
    db: AsyncSession, schema_id: str, data: FormSchemaUpdate
) -> FormSchema:
    schema = await get_schema_by_id(db, schema_id)

    if data.description is not None:
        schema.description = data.description

    if data.fields is not None:
        for f in list(schema.fields):
            await db.delete(f)
        await db.flush()
        for i, f in enumerate(data.fields):
            db.add(FormField(
                schema_id=schema.id,
                name=f.name,
                label=f.label,
                field_type=f.field_type,
                options=f.options,
                default_value=f.default_value,
                is_required=f.is_required,
                position=f.position if f.position else i,
            ))

    await db.flush()
    return await get_schema_by_id(db, schema.id)


# -----------------------------------------------------------------------------

async def delete_schema(db: AsyncSession, schema_id: str) -> None:
    schema = await get_schema_by_id(db, schema_id)
    await db.delete(schema)
    await db.flush()


# ── Topic form assignment ─────────────────────────────────────────────────────

async def assign_form(
    db: AsyncSession, topic: Topic, schema_id: Optional[str]
) -> Topic:
    """Attach or detach a form schema from a topic."""
    if schema_id:
        await get_schema_by_id(db, schema_id)   # validates existence
    topic.form_schema_id = schema_id
    await db.flush()
    return topic


# ── Field values (stored in topic_meta) ──────────────────────────────────────

async def get_field_values(db: AsyncSession, topic_id: str) -> dict[str, str]:
    result = await db.execute(
        select(TopicMeta).where(TopicMeta.topic_id == topic_id)
    )
    return {m.key: m.value for m in result.scalars().all()}


async def set_field_values(
    db: AsyncSession, topic_id: str, values: dict[str, str]
) -> None:
    """Upsert field values into topic_meta."""
    existing_result = await db.execute(
        select(TopicMeta).where(TopicMeta.topic_id == topic_id)
    )
    existing = {m.key: m for m in existing_result.scalars().all()}

    for key, value in values.items():
        if key in existing:
            existing[key].value = value
        else:
            db.add(TopicMeta(topic_id=topic_id, key=key, value=value))

    await db.flush()
