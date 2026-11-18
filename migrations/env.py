from alembic import context

from nutrition.db import Base, make_engine


def run(connection):
    schema = None
    if connection.dialect.name == "postgresql":
        schema = connection.exec_driver_sql("SELECT current_schema()").scalar_one()
    context.configure(
        connection=connection, target_metadata=Base.metadata, version_table_schema=schema
    )
    with context.begin_transaction():
        context.run_migrations()


if context.config.attributes.get("connection") is not None:
    run(context.config.attributes["connection"])
else:
    engine = make_engine()
    with engine.begin() as connection:
        run(connection)
    engine.dispose()
