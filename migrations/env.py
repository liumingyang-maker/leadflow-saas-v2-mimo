from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.modules.accounts.models  # noqa: F401
import app.modules.audit.models  # noqa: F401
import app.modules.inbound.models  # noqa: F401
import app.modules.jobs.models  # noqa: F401
import app.modules.leads.models  # noqa: F401
import app.modules.outreach.models  # noqa: F401
from app.extensions import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def configure_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url and os.environ.get("APP_ENV", "").lower() in {"staging", "production"}:
        raise RuntimeError("DATABASE_URL is required for Alembic migrations in staging/production")

    database_url = database_url or config.get_main_option("sqlalchemy.url")
    config.set_main_option("sqlalchemy.url", database_url)
    return database_url


configure_database_url()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
