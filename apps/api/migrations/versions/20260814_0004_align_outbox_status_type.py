"""Align the outbox status column with the SQLAlchemy enum metadata.

Revision ID: 20260814_0004
Revises: 20260814_0003
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0004"
down_revision = "20260814_0003"
branch_labels = None
depends_on = None


ledger_outbox_status = sa.Enum(
    "PENDING",
    "SUBMITTED",
    "COMMITTED",
    "FAILED",
    name="ledger_outbox_status",
    native_enum=False,
    create_constraint=False,
)


def upgrade() -> None:
    op.alter_column(
        "ledger_outbox",
        "status",
        existing_type=sa.String(length=16),
        type_=ledger_outbox_status,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "ledger_outbox",
        "status",
        existing_type=ledger_outbox_status,
        type_=sa.String(length=16),
        existing_nullable=False,
    )
