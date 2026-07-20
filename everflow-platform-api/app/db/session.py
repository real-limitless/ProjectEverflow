"""Async engine and session factory. Supports SQLite and PostgreSQL via DATABASE_URL."""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _make_engine(settings: Settings) -> AsyncEngine:
    url = settings.database_url
    kwargs: dict = {
        "echo": settings.debug and settings.environment == "development",
    }

    if url.startswith("sqlite"):
        # In-memory needs StaticPool so the same connection is reused across sessions.
        if ":memory:" in url:
            kwargs["connect_args"] = {"check_same_thread": False}
            kwargs["poolclass"] = StaticPool
        else:
            kwargs["connect_args"] = {"check_same_thread": False}
            kwargs["poolclass"] = NullPool
    elif settings.environment == "test":
        kwargs["poolclass"] = NullPool

    engine = create_async_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_db(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Create (or recreate) the global engine and session factory."""
    global _engine, _session_factory
    settings = settings or get_settings()

    if _engine is not None:
        # Caller should await dispose_db() first for clean re-init (tests).
        pass

    _engine = _make_engine(settings)
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return _session_factory


def get_engine() -> AsyncEngine:
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    return _session_factory


async def dispose_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
