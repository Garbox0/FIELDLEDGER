"""Create assets table.

Revision ID: 20260814_0001
Revises:
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("site", sa.String(length=160), nullable=False),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("manufacturer", sa.String(length=160), nullable=True),
        sa.Column("serial_number", sa.String(length=128), nullable=True),
        sa.Column("operator", sa.String(length=160), nullable=True),
        sa.Column("installation_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "MAINTENANCE",
                "OUT_OF_SERVICE",
                "DECOMMISSIONED",
                name="asset_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "criticality",
            sa.Enum(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="asset_criticality",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("asset_id"),
    )
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_criticality", "assets", ["criticality"])
    op.create_index("ix_assets_serial_number", "assets", ["serial_number"])
    op.create_index("ix_assets_site", "assets", ["site"])
    op.create_index("ix_assets_status", "assets", ["status"])


def downgrade() -> None:
    op.drop_index("ix_assets_status", table_name="assets")
    op.drop_index("ix_assets_site", table_name="assets")
    op.drop_index("ix_assets_serial_number", table_name="assets")
    op.drop_index("ix_assets_criticality", table_name="assets")
    op.drop_index("ix_assets_asset_type", table_name="assets")
    op.drop_table("assets")
