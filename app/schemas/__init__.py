"""
Pydantic v2 schemas for request validation and response serialisation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Shared
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class OKResponse(BaseModel):
    ok: bool = True
    message: str = "success"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Auth
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int   # seconds


# -----------------------------------------------------------------------------

class RefreshRequest(BaseModel):
    refresh_token: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Users
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    display_name: str = Field(default="", max_length=128)

    @field_validator("username")
    @classmethod
    def username_not_reserved(cls, v: str) -> str:
        reserved = {"system", "guest", "anonymous"}
        if v.lower() in reserved:
            raise ValueError(f"Username '{v}' is reserved")
        return v


# -----------------------------------------------------------------------------

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    display_name: Optional[str] = Field(None, max_length=128)
    password: Optional[str] = Field(None, min_length=8, max_length=256)


# -----------------------------------------------------------------------------

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    display_name: str
    wiki_name: str
    is_admin: bool
    groups: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Webs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WebCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    description: str = Field(default="", max_length=1000)
    parent_name: Optional[str] = None


# -----------------------------------------------------------------------------

class WebUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=1000)


# -----------------------------------------------------------------------------

class WebResponse(BaseModel):
    id: str
    name: str
    description: str
    parent_id: Optional[str]
    created_at: datetime
    topic_count: Optional[int] = None

    model_config = {"from_attributes": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Topics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TopicCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    content: str = Field(default="", max_length=10_000_000)  # 10 MB
    comment: str = Field(default="", max_length=512)
    meta: dict[str, str] = Field(default_factory=dict)


# -----------------------------------------------------------------------------

class TopicUpdate(BaseModel):
    content: str = Field(..., max_length=10_000_000)
    comment: str = Field(default="", max_length=512)
    meta: Optional[dict[str, str]] = None


# -----------------------------------------------------------------------------

class TopicRename(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=256, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")


# -----------------------------------------------------------------------------

class TopicVersionResponse(BaseModel):
    id: str
    version: int
    content: str
    author_id: Optional[str]
    author_username: Optional[str]
    comment: str
    created_at: datetime

    model_config = {"from_attributes": True}


# -----------------------------------------------------------------------------

class TopicResponse(BaseModel):
    id: str
    web: str
    name: str
    version: int
    content: str
    rendered: Optional[str]
    author_id: Optional[str]
    author_username: Optional[str]
    comment: str
    meta: dict[str, str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# -----------------------------------------------------------------------------

class TopicSummary(BaseModel):
    """Lightweight listing item — no content body."""
    id: str
    web: str
    name: str
    version: int
    author_username: Optional[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiffResponse(BaseModel):
    web: str
    topic: str
    from_version: int
    to_version: int
    diff: list[dict]   # list of {type: "equal"|"insert"|"delete", lines: [...]}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Attachments
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AttachmentResponse(BaseModel):
    id: str
    topic_id: str
    filename: str
    content_type: str
    size_bytes: int
    comment: str
    uploaded_by: Optional[str]
    uploaded_at: datetime
    url: str

    model_config = {"from_attributes": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DataForms
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FIELD_TYPES = {"text", "textarea", "number", "date", "select", "multiselect", "checkbox", "url", "email"}


class FormFieldCreate(BaseModel):
    name:          str  = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    label:         str  = Field(..., min_length=1, max_length=256)
    field_type:    str  = Field(default="text")
    options:       str  = Field(default="", max_length=2000)   # comma-sep for select/multiselect
    default_value: str  = Field(default="", max_length=2000)
    is_required:   bool = False
    position:      int  = Field(default=0, ge=0)

    @field_validator("field_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in FIELD_TYPES:
            raise ValueError(f"field_type must be one of: {', '.join(sorted(FIELD_TYPES))}")
        return v


class FormFieldResponse(BaseModel):
    id:            str
    schema_id:     str
    name:          str
    label:         str
    field_type:    str
    options:       str
    default_value: str
    is_required:   bool
    position:      int

    model_config = {"from_attributes": True}


class FormSchemaCreate(BaseModel):
    name:        str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z][A-Za-z0-9_\- ]*$")
    description: str = Field(default="", max_length=1000)
    web_name:    Optional[str] = None   # None = global schema
    fields:      list[FormFieldCreate] = Field(default_factory=list)


class FormSchemaUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=1000)
    fields:      Optional[list[FormFieldCreate]] = None   # if provided, replaces all fields


class FormSchemaResponse(BaseModel):
    id:          str
    name:        str
    description: str
    web_id:      Optional[str]
    web_name:    Optional[str] = None
    fields:      list[FormFieldResponse]
    created_at:  datetime
    updated_at:  datetime

    model_config = {"from_attributes": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ACL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ACLEntry(BaseModel):
    principal: str = Field(..., description="'user:jdoe', 'group:Dev', or '*'")
    permission: str = Field(..., pattern=r"^(view|edit|create|rename|delete|admin)$")
    allow: bool = True


# -----------------------------------------------------------------------------

class ACLUpdate(BaseModel):
    entries: list[ACLEntry]


# -----------------------------------------------------------------------------

class ACLResponse(BaseModel):
    resource_type: str
    resource_id: str
    entries: list[ACLEntry]


# -----------------------------------------------------------------------------

