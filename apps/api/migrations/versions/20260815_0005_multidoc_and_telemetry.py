"""Support multi-documents per event, asset decommission, and telemetry batches.

Revision ID: 20260815_0005
Revises: 20260814_0004
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0005"
down_revision = "20260814_0004"
branch_labels = None
depends_on = None


document_category = sa.Enum(
    "WORK_ORDER",
    "CALIBRATION_CERT",
    "INSPECTION_PHOTO",
    "NDT_REPORT",
    "LAB_ANALYSIS",
    "DECOMMISSION_RECORD",
    "OTHER",
    name="document_category",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)

batch_ledger_status = sa.Enum(
    "PENDING",
    "SUBMITTED",
    "COMMITTED",
    "FAILED",
    name="batch_ledger_status",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)


def upgrade() -> None:
    # 1. Assets updates
    op.add_column(
        "assets",
        sa.Column("decommissioned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("decommission_reason", sa.Text(), nullable=True),
    )

    # 2. Asset documents updates
    with op.batch_alter_table("asset_documents") as batch_op:
        try:
            batch_op.drop_constraint("asset_documents_event_id_key", type_="unique")
        except Exception:
            pass
        batch_op.add_column(
            sa.Column(
                "category",
                document_category,
                nullable=False,
                server_default="OTHER",
            )
        )
        batch_op.add_column(
            sa.Column("notes", sa.String(length=500), nullable=True)
        )
        batch_op.create_index("ix_asset_documents_category", ["category"])

    # 3. Telemetry batches table
    op.create_table(
        "telemetry_batches",
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reading_count", sa.Integer(), nullable=False),
        sa.Column("merkle_root", sa.String(length=64), nullable=False),
        sa.Column("ledger_tx_id", sa.String(length=128), nullable=True),
        sa.Column("ledger_status", batch_ledger_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("batch_id"),
        sa.UniqueConstraint("ledger_tx_id"),
    )
    op.create_index("ix_telemetry_batches_asset_id", "telemetry_batches", ["asset_id"])
    op.create_index("ix_telemetry_batches_merkle_root", "telemetry_batches", ["merkle_root"])
    op.create_index("ix_telemetry_batches_ledger_status", "telemetry_batches", ["ledger_status"])

    # 4. Telemetry readings table
    op.create_table(
        "telemetry_readings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("pressure_psi", sa.Float(), nullable=True),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("vibration_mms", sa.Float(), nullable=True),
        sa.Column("flow_rate_bpd", sa.Float(), nullable=True),
        sa.Column("batch_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["telemetry_batches.batch_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_telemetry_readings_asset_id", "telemetry_readings", ["asset_id"])
    op.create_index("ix_telemetry_readings_timestamp", "telemetry_readings", ["timestamp"])
    op.create_index("ix_telemetry_readings_batch_id", "telemetry_readings", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_telemetry_readings_batch_id", table_name="telemetry_readings")
    op.drop_index("ix_telemetry_readings_timestamp", table_name="telemetry_readings")
    op.drop_index("ix_telemetry_readings_asset_id", table_name="telemetry_readings")
    op.drop_table("telemetry_readings")

    op.drop_index("ix_telemetry_batches_ledger_status", table_name="telemetry_batches")
    op.drop_index("ix_telemetry_batches_merkle_root", table_name="telemetry_batches")
    op.drop_index("ix_telemetry_batches_asset_id", table_name="telemetry_batches")
    op.drop_table("telemetry_batches")

    with op.batch_alter_table("asset_documents") as batch_op:
        batch_op.drop_index("ix_asset_documents_category")
        batch_op.drop_column("notes")
        batch_op.drop_column("category")
        batch_op.create_unique_constraint("asset_documents_event_id_key", ["event_id"])

    op.drop_column("assets", "decommission_reason")
    op.drop_column("assets", "decommissioned_at")
