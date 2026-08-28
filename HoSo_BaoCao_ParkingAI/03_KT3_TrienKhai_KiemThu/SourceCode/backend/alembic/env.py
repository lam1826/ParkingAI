"""Alembic environment for the managed PostgreSQL production database.

SQLite keeps its existing explicit rollout path.  Mixing the two migration
systems would make it too easy to run PostgreSQL DDL against a local legacy
file (or vice versa), so this environment deliberately fails closed.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from database import Base
import models  # noqa: F401 - registers every model with Base.metadata


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("DATABASE_URL", "").strip()
if database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
if not database_url.startswith("postgresql+psycopg://"):
    raise RuntimeError(
        "Alembic production migrations require DATABASE_URL to be an explicit "
        "PostgreSQL URL; SQLite uses db_rollout.py instead."
    )

config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    if connectable.dialect.name != "postgresql":
        raise RuntimeError("Alembic production migrations only support PostgreSQL")

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
