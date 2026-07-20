"""Alembic environment — async, dual SQLite/Postgres via DATABASE_URL."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import String, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.db.base import Base
from app.models import (  # noqa: F401 — register metadata
    OAuthAccount,
    Organization,
    OrganizationMember,
    Project,
    User,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def _is_guid_like(type_) -> bool:
    """True for fastapi-users GUID and portable VARCHAR/CHAR(36) UUID storage."""
    name = type(type_).__name__
    if name == "GUID":
        return True
    if isinstance(type_, String) and getattr(type_, "length", None) == 36:
        return True
    # Dialect-reflected CHAR(36) / VARCHAR(36)
    impl = getattr(type_, "impl", None)
    if impl is not None and isinstance(impl, String) and getattr(impl, "length", None) == 36:
        return True
    return False


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):  # noqa: ANN001, ARG001
    """Avoid false positives: migration uses String(36), models use GUID (same storage)."""
    if _is_guid_like(inspected_type) and _is_guid_like(metadata_type):
        return False
    # None = use Alembic default comparison
    return None


def _configure_context(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=compare_type,
        **kwargs,
    )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    _configure_context(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite") if url else False,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    url = config.get_main_option("sqlalchemy.url") or ""
    _configure_context(
        connection=connection,
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
