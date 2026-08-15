"""Add the durable Fabric ledger outbox.

Revision ID: 20260814_0003
Revises: 20260814_0002
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0003"
down_revision = "20260814_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ledger_outbox",
        sa.Column("operation_id", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=32), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("organization", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("ledger_tx_id", sa.String(length=128), nullable=True),
        sa.Column("block_number", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("action IN ('REGISTER_ASSET', 'PROPOSE_EVENT', 'REVIEW_EVENT', 'REGISTER_DOCUMENT')", name="ledger_outbox_action"),
        sa.CheckConstraint("status IN ('PENDING', 'SUBMITTED', 'COMMITTED', 'FAILED')", name="ledger_outbox_status"),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_index("ix_ledger_outbox_action", "ledger_outbox", ["action"])
    op.create_index("ix_ledger_outbox_aggregate_id", "ledger_outbox", ["aggregate_id"])
    op.create_index("ix_ledger_outbox_aggregate_type", "ledger_outbox", ["aggregate_type"])
    op.create_index("ix_ledger_outbox_ledger_tx_id", "ledger_outbox", ["ledger_tx_id"])
    op.create_index("ix_ledger_outbox_next_attempt_at", "ledger_outbox", ["next_attempt_at"])
    op.create_index("ix_ledger_outbox_status", "ledger_outbox", ["status"])


def downgrade() -> None:
    op.drop_table("ledger_outbox")
