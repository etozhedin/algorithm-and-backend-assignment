"""Create nutrition records with uniqueness, validation, and search indexes."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NUTRIENTS = (
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


def upgrade():
    op.create_table(
        "foods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("food_cd", sa.String(100), nullable=False),
        sa.Column("food_name", sa.String(500), nullable=False),
        sa.Column("group_name", sa.String(500)),
        sa.Column("research_year", sa.Integer()),
        sa.Column("maker_name", sa.String(500)),
        sa.Column("ref_name", sa.String(500)),
        *(sa.Column(name, sa.Float()) for name in NUTRIENTS),
        sa.UniqueConstraint("food_cd", name="uq_foods_food_cd"),
        sa.CheckConstraint("research_year IS NULL OR research_year BETWEEN 1 AND 9999"),
        *(sa.CheckConstraint(f"{name} IS NULL OR {name} >= 0") for name in NUTRIENTS),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_foods_research_year_id", "foods", ["research_year", "id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
        for field in ("food_name", "maker_name"):
            op.create_index(
                f"ix_foods_{field}_trgm",
                "foods",
                [field],
                postgresql_using="gin",
                postgresql_ops={field: "gin_trgm_ops"},
            )


def downgrade():
    op.drop_table("foods")
    # pg_trgm can be shared by other applications; leave the extension installed.
