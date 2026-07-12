from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the metadata and every model module so autogenerate sees the full
# schema — SQLAlchemy only registers a table on Base.metadata once its model
# module has actually been imported.
from verdantis.config.settings import get_settings
from verdantis.db.base import Base
from verdantis.db import models  # noqa: F401  # registers Tenant/Company/... on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# The URL never lives in alembic.ini (rule 6: no secrets in code or git) —
# it's read from Settings, same as the app runtime, just via the sync driver.
# A caller invoking Alembic programmatically (e.g. the test suite pointing at
# verdantis_test) may already have set sqlalchemy.url on this Config before
# env.py runs — respect that instead of clobbering it with the dev URL.
if config.get_main_option("sqlalchemy.url") is None:
    config.set_main_option("sqlalchemy.url", get_settings().sync_database_url)


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
