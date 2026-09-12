"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_items",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_table(
        "catalog_variations",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "item_id",
            sa.Text,
            sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("variation_name", sa.Text, nullable=False),
        sa.Column("sku", sa.Text),
        sa.Column("price", sa.Integer),
        sa.Column("pricing_type", sa.Text, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("catalog_variations_item_id", "catalog_variations", ["item_id"])
    op.create_table(
        "sync_cursors",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("latest_time", sa.Text, nullable=False),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column(
            "variation_id",
            sa.Text,
            sa.ForeignKey("catalog_variations.id", ondelete="SET NULL"),
        ),
        sa.Column("content_hash", sa.Text),
        sa.Column("last_pushed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_confirmed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("battery_pct", sa.SmallInteger),
    )


def downgrade() -> None:
    op.drop_table("tags")
    op.drop_index("catalog_variations_item_id", table_name="catalog_variations")
    op.drop_table("catalog_variations")
    op.drop_table("sync_cursors")
    op.drop_table("catalog_items")
