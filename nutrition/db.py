import os
from pathlib import Path

from sqlalchemy import CheckConstraint, Float, Index, Integer, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (
        CheckConstraint("research_year IS NULL OR research_year BETWEEN 1 AND 9999"),
        *(
            CheckConstraint(f"{field} IS NULL OR {field} >= 0")
            for field in (
                "serving_size",
                "calorie",
                "carbohydrate",
                "protein",
                "fat",
                "sugars",
                "sodium",
                "cholesterol",
                "saturated_fatty_acids",
                "trans_fat",
            )
        ),
        Index("ix_foods_research_year_id", "research_year", "id"),
        *(
            Index(
                f"ix_foods_{field}_trgm",
                field,
                postgresql_using="gin",
                postgresql_ops={field: "gin_trgm_ops"},
            ).ddl_if(dialect="postgresql")
            for field in ("food_name", "maker_name")
        ),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_cd: Mapped[str] = mapped_column(String(100), unique=True)
    food_name: Mapped[str] = mapped_column(String(500))
    group_name: Mapped[str | None] = mapped_column(String(500))
    research_year: Mapped[int | None] = mapped_column(Integer)
    maker_name: Mapped[str | None] = mapped_column(String(500))
    ref_name: Mapped[str | None] = mapped_column(String(500))
    serving_size: Mapped[float | None] = mapped_column(Float)
    calorie: Mapped[float | None] = mapped_column(Float)
    carbohydrate: Mapped[float | None] = mapped_column(Float)
    protein: Mapped[float | None] = mapped_column(Float)
    fat: Mapped[float | None] = mapped_column(Float)
    sugars: Mapped[float | None] = mapped_column(Float)
    sodium: Mapped[float | None] = mapped_column(Float)
    cholesterol: Mapped[float | None] = mapped_column(Float)
    saturated_fatty_acids: Mapped[float | None] = mapped_column(Float)
    trans_fat: Mapped[float | None] = mapped_column(Float)


def make_engine(url=None):
    url = url or os.getenv(
        "DATABASE_URL", "postgresql+psycopg://nutrition:nutrition@localhost:5432/nutrition"
    )
    if url.startswith("postgresql+psycopg://"):
        return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    if not url.startswith("sqlite:///"):
        raise ValueError("Use a postgresql+psycopg:// or sqlite:/// DATABASE_URL")
    database = url.removeprefix("sqlite:///")
    if database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def initialize(engine):
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
