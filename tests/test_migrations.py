from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from nutrition.db import initialize


def current_schema(connection):
    if connection.dialect.name == "postgresql":
        return connection.exec_driver_sql("SELECT current_schema()").scalar_one()
    return None


def test_migrations_are_reversible_and_repeatable(app):
    engine = app.state.engine
    initialize(engine)
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert "foods" not in inspect(connection).get_table_names(schema=current_schema(connection))
        command.upgrade(config, "head")
        assert "foods" in inspect(connection).get_table_names(schema=current_schema(connection))


def test_standalone_migration_commits(app):
    import os
    import subprocess
    import sys

    engine = app.state.engine
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    environment = {**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False)}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
    )
    with engine.connect() as connection:
        assert "foods" in inspect(connection).get_table_names(schema=current_schema(connection))
