"""Run the Alembic migrations against a real Postgres and check the models match them.

Skipped unless TEST_POSTGRES_URL points at an empty, disposable database (CI provides one).
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from itk.db import Base, make_engine

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")
BACKEND = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set")


def _alembic(url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.attributes["database_url"] = url
    return config


def test_migrations_upgrade_downgrade_and_match_models() -> None:
    assert POSTGRES_URL
    engine = make_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))

    config = _alembic(POSTGRES_URL)
    command.upgrade(config, "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine.dispose()
