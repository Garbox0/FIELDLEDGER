"""Update ledger_outbox_action check constraint to include DECOMMISSION_ASSET and REGISTER_TELEMETRY_BATCH.

Revision ID: 20260816_0006
Revises: 20260815_0005
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0006"
down_revision = "20260815_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing check constraint and add updated one with new actions
    try:
        op.drop_constraint("ledger_outbox_action", "ledger_outbox", type_="check")
    except Exception:
        pass

    op.create_check_constraint(
        "ledger_outbox_action",
        "ledger_outbox",
        "action IN ('REGISTER_ASSET', 'PROPOSE_EVENT', 'REVIEW_EVENT', 'REGISTER_DOCUMENT', 'DECOMMISSION_ASSET', 'REGISTER_TELEMETRY_BATCH')",
    )


def downgrade() -> None:
    try:
        op.drop_constraint("ledger_outbox_action", "ledger_outbox", type_="check")
    except Exception:
        pass

    op.create_check_constraint(
        "ledger_outbox_action",
        "ledger_outbox",
        "action IN ('REGISTER_ASSET', 'PROPOSE_EVENT', 'REVIEW_EVENT', 'REGISTER_DOCUMENT')",
    )
