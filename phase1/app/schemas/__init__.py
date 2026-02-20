#!/usr/bin/env pythpon
#
#
# -----------------------------------------------------------------------------

"""
Pydantic v2 schemas for request/response validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Auth
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_\-\.]+$")
    email: EmailStr
    display_name: str = Field(default="", max_length=128)
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    display_name: str
    wiki_name: str
    is_active: bool
    is_admin: bool
    groups: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, user) -> "UserOut":
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            wiki_name=user.wiki_name,
            is_active=user.is_active,
            is_admin=user.is_admin,
            groups=user.groups,
            created_at=user.created_at,
        )


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=128)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=8)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Web
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WebCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z][A-Za-z0-9_\-]*$")
    description: str = Field(default="", max_length=1024)
    parent_id: Optional[uuid.UUID] = None


class WebUpdate(BaseModel):
    description: Optional[str] = Field(default=None, max_length=1024)


class WebOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    parent_id: Optional[uuid.UUID]
    created_at: datetime
    topic_count: int = 0

    model_config = {"from_attributes": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Topic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TopicCreate(BaseModel):
    name: str = Field(
        min_length=1, max_length=255,
        pattern=r"^[A-Za-z][A-Za-z0-9_\-]*$",
        description="WikiWord or slug; starts with a letter",
    )
    content: str = Field(default="")
    comment: str = Field(default="Initial version", max_length=512)
    meta: dict[str, str] = Field(default_factory=dict)


class TopicSave(BaseModel):
    """Payload for saving a new version of an existing topic."""
    content: str
    comment: str = Field(default="", max_length=512)
    meta: Optional[dict[str, str]] = None   # if None, meta is unchanged


class TopicOut(BaseModel):
    id: uuid.UUID
    web_id: uuid.UUID
    web_name: str
    name: str
    created_at: datetime
    current_version: int
    modified_at: datetime
    modified_by: Optional[str]   # username
    content: str
    meta: dict[str, str] = {}

    model_config = {"from_attributes": True}


class TopicListItem(BaseModel):
    id: uuid.UUID
    name: str
    current_version: int
    modified_at: datetime
    modified_by: Optional[str]

    model_config = {"from_attributes": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Topic Version / History
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class VersionOut(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID
    version: int
    comment: str
    author: Optional[str]
    created_at: datetime
    content: Optional[str] = None   # included only when fetching a specific version

    model_config = {"from_attributes": True}


class DiffOut(BaseModel):
    web: str
    topic: str
    from_version: int
    to_version: int
    unified_diff: str   # unified diff text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Attachment
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AttachmentOut(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID
    filename: str
    original_filename: str
    content_type: str
    size_bytes: int
    comment: str
    uploaded_by: Optional[str]
    uploaded_at: datetime
    download_url: str

    model_config = {"from_attributes": True}





