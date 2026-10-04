"""gateway command queue, telemetry, and catalog currency

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Square gives a currency alongside every price; the gateway's Money
    # schema requires one. Existing rows are backfilled to USD.
    op.add_column("catalog_variations", sa.Column("currency", sa.Text, nullable=True))
    op.execute("UPDATE catalog_variations SET currency = 'USD' WHERE currency IS NULL")

    # Per-tag version ladder. Existing tags start at 0 so the first command
    # generated for them is version 1.
    op.add_column(
        "tags",
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "label_commands",
        sa.Column("update_id", sa.Text, primary_key=True),
        sa.Column(
            "store_id",
            sa.Text,
            sa.ForeignKey("stores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tag_id",
            sa.Text,
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=True),
        sa.Column("product_id", sa.Text, nullable=True),
        sa.Column("display", postgresql.JSONB, nullable=True),
        sa.Column("seconds", sa.Integer, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("status_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer, nullable=True),
        sa.Column("ap_id", sa.Text, nullable=True),
        sa.Column("failure_code", sa.Text, nullable=True),
        sa.Column("failure_message", sa.Text, nullable=True),
        sa.Column("retryable", sa.Boolean, nullable=True),
        sa.Column("diagnostics", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "label_commands_store_status_created",
        "label_commands",
        ["store_id", "status", "created_at"],
    )
    op.create_index("label_commands_tag_id", "label_commands", ["tag_id"])

    op.create_table(
        "label_telemetry",
        sa.Column(
            "store_id",
            sa.Text,
            sa.ForeignKey("stores.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tag_id", sa.Text, primary_key=True),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_seen_ap_id", sa.Text, nullable=True),
        sa.Column("rf_power", sa.Integer, nullable=True),
        sa.Column("battery", sa.Integer, nullable=True),
        sa.Column("low_battery", sa.Boolean, nullable=True),
        sa.Column("temperature", sa.Integer, nullable=True),
        sa.Column("status_byte", sa.Integer, nullable=True),
        sa.Column("firmware_version", sa.Integer, nullable=True),
        sa.Column("screen_type", sa.Integer, nullable=True),
        sa.Column("size", sa.Integer, nullable=True),
        sa.Column("color", sa.Integer, nullable=True),
        sa.Column("factory", sa.Integer, nullable=True),
        sa.Column("last_success_ap_id", sa.Text, nullable=True),
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_result_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_result_success", sa.Boolean, nullable=True),
        sa.Column("reported_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "access_point_telemetry",
        sa.Column(
            "store_id",
            sa.Text,
            sa.ForeignKey("stores.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("ap_id", sa.Text, primary_key=True),
        sa.Column("connected", sa.Boolean, nullable=False),
        sa.Column("stale", sa.Boolean, nullable=False),
        sa.Column("connected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("heartbeat_interval_seconds", sa.Integer, nullable=True),
        sa.Column("ap_version", sa.Text, nullable=True),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("wait_count", sa.Integer, nullable=True),
        sa.Column("send_count", sa.Integer, nullable=True),
        sa.Column("reported_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("access_point_telemetry")
    op.drop_table("label_telemetry")
    op.drop_index("label_commands_tag_id", table_name="label_commands")
    op.drop_index("label_commands_store_status_created", table_name="label_commands")
    op.drop_table("label_commands")
    op.drop_column("tags", "version")
    op.drop_column("catalog_variations", "currency")
