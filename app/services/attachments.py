#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Attachment service
==================
Handles file uploads to disk, tracking metadata in the database.

Storage layout (all paths relative to settings.attachment_root):
  {web}/{topic}/{filename}

Filenames are sanitised before use. Overwrites are allowed (same topic+filename).
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# -----------------------------------------------------------------------------

from app.core.config import get_settings
from app.models import Attachment, Topic, Web
from .webs import get_web_by_name
from .topics import get_topic  # used to verify topic exists


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Filename sanitisation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_UNSAFE = re.compile(r"[^\w.\-]")
_DOTDOT = re.compile(r"\.{2,}")


# -----------------------------------------------------------------------------

def sanitise_filename(name: str) -> str:
    """Return a safe, filesystem-friendly filename."""
    name = Path(name).name          # strip directory components
    name = _UNSAFE.sub("_", name)   # replace unsafe chars
    name = _DOTDOT.sub(".", name)   # collapse multiple dots
    name = name.strip("._")         # strip leading/trailing dots and underscores
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if len(name) > 255:
        raise HTTPException(status_code=400, detail="Filename too long (max 255 chars)")
    return name


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Upload
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def upload_attachment(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
    upload: UploadFile,
    comment: str = "",
    author_id: Optional[str] = None,
) -> Attachment:
    settings = get_settings()

    # Resolve topic
    web = await get_web_by_name(db, web_name)
    topic_row, _ver = await get_topic(db, web_name, topic_name)

    safe_name = sanitise_filename(upload.filename or "upload")
    content_type = upload.content_type or _guess_content_type(safe_name)

    # Destination path
    rel_path  = f"{web_name}/{topic_name}/{safe_name}"
    full_path = settings.attachment_root_resolved / web_name / topic_name / safe_name
    full_path.parent.mkdir(parents=True, exist_ok=True)

    # Stream file to disk, enforce size limit
    max_bytes = settings.max_attachment_bytes
    written   = 0
    try:
        async with aiofiles.open(full_path, "wb") as fh:
            while chunk := await upload.read(65_536):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Attachment exceeds maximum size ({max_bytes // 1024 // 1024} MB)",
                    )
                await fh.write(chunk)
    except HTTPException:
        full_path.unlink(missing_ok=True)   # clean up partial file
        raise

    # Upsert DB record (same topic+filename replaces the old entry)
    result = await db.execute(
        select(Attachment).where(
            Attachment.topic_id == topic_row.id,
            Attachment.filename == safe_name,
        )
    )
    attachment = result.scalar_one_or_none()

    if attachment:
        attachment.size_bytes   = written
        attachment.content_type = content_type
        attachment.storage_path = rel_path
        attachment.uploaded_by  = author_id
        attachment.comment      = comment
    else:
        attachment = Attachment(
            topic_id=topic_row.id,
            filename=safe_name,
            content_type=content_type,
            size_bytes=written,
            storage_path=rel_path,
            uploaded_by=author_id,
            comment=comment,
        )
        db.add(attachment)

    await db.flush()
    return attachment


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# List / get / delete
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def list_attachments(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
) -> list[Attachment]:
    _web = await get_web_by_name(db, web_name)
    topic_row, _ver = await get_topic(db, web_name, topic_name)

    result = await db.execute(
        select(Attachment)
        .where(Attachment.topic_id == topic_row.id)
        .order_by(Attachment.filename)
    )
    return list(result.scalars().all())


# -----------------------------------------------------------------------------

async def get_attachment(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
    filename: str,
) -> tuple[Attachment, Path]:
    """Return (attachment_record, full_disk_path)."""
    settings = get_settings()
    topic_row, _ver = await get_topic(db, web_name, topic_name)

    result = await db.execute(
        select(Attachment).where(
            Attachment.topic_id == topic_row.id,
            Attachment.filename == filename,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail=f"Attachment '{filename}' not found")

    full_path = settings.attachment_root_resolved / attachment.storage_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file missing from storage")

    return attachment, full_path


# -----------------------------------------------------------------------------

async def delete_attachment(
    db: AsyncSession,
    web_name: str,
    topic_name: str,
    filename: str,
) -> None:
    settings = get_settings()
    attachment, full_path = await get_attachment(db, web_name, topic_name, filename)
    full_path.unlink(missing_ok=True)
    await db.delete(attachment)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _guess_content_type(filename: str) -> str:
    ct, _ = mimetypes.guess_type(filename)
    return ct or "application/octet-stream"


# -----------------------------------------------------------------------------

