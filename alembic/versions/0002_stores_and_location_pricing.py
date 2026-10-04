"""stores and location pricing

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("square_location_id", sa.Text, nullable=False, unique=True),
        sa.Column("api_key", sa.Text, nullable=False, unique=True),
    )
    op.create_table(
        "catalog_variation_location_prices",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "variation_id",
            sa.Text,
            sa.ForeignKey("catalog_variations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("square_location_id", sa.Text, nullable=False),
        sa.Column("price", sa.Integer, nullable=False),
        sa.UniqueConstraint("variation_id", "square_location_id"),
    )

    # tags.id shrinks from 16 to 12 hex chars to match real ESL hardware ids.
    op.alter_column("tags", "id", type_=sa.String(12))

    op.add_column("tags", sa.Column("store_id", sa.Text, nullable=False))
    op.create_foreign_key(
        "tags_store_id_fkey", "tags", "stores", ["store_id"], ["id"], ondelete="RESTRICT"
    )


def downgrade() -> None:
    op.drop_constraint("tags_store_id_fkey", "tags", type_="foreignkey")
    op.drop_column("tags", "store_id")
    op.alter_column("tags", "id", type_=sa.String(16))
    op.drop_table("catalog_variation_location_prices")
    op.drop_table("stores")
