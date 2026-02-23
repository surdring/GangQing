from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from gangqing_db.settings import load_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Schema-first note: migrations are authoritative for DB objects in Task 5.1.
# We intentionally do not rely on ORM model metadata here.
target_metadata = None

_VERSION_TABLE = "gangqing_alembic_version"


def get_url() -> str:
    settings = load_settings()
    return settings.database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=_VERSION_TABLE,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=_VERSION_TABLE,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
