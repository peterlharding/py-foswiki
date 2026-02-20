#!/usr/bin/env python
#
#
# -----------------------------------------------------------------------------
"""
Database engine and session factory.

Usage in FastAPI:

    @app.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Topic))
        ...
"""
# -----------------------------------------------------------------------------

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


# -----------------------------------------------------------------------------

from .config import get_settings


# -----------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# -----------------------------------------------------------------------------

def _make_engine(url: str | None = None, echo: bool | None = None):
    settings = get_settings()
    db_url   = url   or settings.database_url
    db_echo  = echo  if echo is not None else settings.db_echo

    kwargs: dict = {}
    if "sqlite" not in db_url:
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )

    return create_async_engine(db_url, echo=db_echo, **kwargs)


# -----------------------------------------------------------------------------
# Module-level singletons (overridden in tests via override_engine())

_engine = None
_session_factory = None


# -----------------------------------------------------------------------------

def init_db(url: str | None = None, echo: bool | None = None) -> None:
    """Initialise the engine and session factory.  Call once at startup."""
    global _engine, _session_factory
    _engine = _make_engine(url, echo)
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# -----------------------------------------------------------------------------

def get_engine():
    if _engine is None:
        init_db()
    return _engine


# -----------------------------------------------------------------------------

def get_session_factory():
    if _session_factory is None:
        init_db()
    return _session_factory


# -----------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# -----------------------------------------------------------------------------

async def create_all_tables() -> None:
    """Create all tables (dev / test only — use Alembic in production)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# -----------------------------------------------------------------------------

async def drop_all_tables() -> None:
    """Drop all tables (tests only)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# -----------------------------------------------------------------------------

