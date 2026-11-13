from logging.config import fileConfig

from sqlalchemy import pool

import itk.models  # noqa: F401  (registers every table on Base.metadata)
from alembic import context
from itk.config import get_settings
from itk.db import Base, make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# Migrations go through the unpooled connection when one is configured (Neon's pooler
# does not support the session-level features Alembic relies on).
database_url = config.attributes.get("database_url") or settings.database_url_unpooled or settings.database_url
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
