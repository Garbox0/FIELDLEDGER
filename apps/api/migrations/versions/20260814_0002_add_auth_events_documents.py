"""Add organizations, users, maintenance events, and documents.

Revision ID: 20260814_0002
Revises: 20260814_0001
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0002"
down_revision = "20260814_0001"
branch_labels = None
depends_on = None


organization_type = sa.Enum(
    "OPERATOR",
    "CONTRACTOR",
    "AUDITOR",
    name="organization_type",
    native_enum=False,
    create_constraint=True,
)
app_role = sa.Enum(
    "ADMIN",
    "OPERATOR",
    "CONTRACTOR",
    "AUDITOR",
    "VIEWER",
    name="app_role",
    native_enum=False,
    create_constraint=True,
)
asset_event_type = sa.Enum(
    "INSTALLATION",
    "INSPECTION",
    "PREVENTIVE_MAINTENANCE",
    "CORRECTIVE_MAINTENANCE",
    "PART_REPLACEMENT",
    "PRESSURE_TEST",
    "CALIBRATION",
    "CERTIFICATION",
    "FAILURE",
    "RETURN_TO_SERVICE",
    "DECOMMISSION",
    name="asset_event_type",
    native_enum=False,
    create_constraint=True,
)
event_status = sa.Enum(
    "PROPOSED",
    "APPROVED",
    "REJECTED",
    name="event_status",
    native_enum=False,
    create_constraint=True,
)
ledger_status = sa.Enum(
    "PENDING",
    "SUBMITTED",
    "COMMITTED",
    "FAILED",
    name="ledger_status",
    native_enum=False,
    create_constraint=True,
)
document_ledger_status = sa.Enum(
    "PENDING",
    "SUBMITTED",
    "COMMITTED",
    "FAILED",
    name="document_ledger_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("organization_type", organization_type, nullable=False),
        sa.Column("fabric_msp_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("organization_id"),
        sa.UniqueConstraint("fabric_msp_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "users",
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", app_role, nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.organization_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("username"),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "asset_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", asset_event_type, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("organization", sa.String(length=160), nullable=False),
        sa.Column("performed_by", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", event_status, nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=True),
        sa.Column("ledger_tx_id", sa.String(length=128), nullable=True),
        sa.Column("ledger_status", ledger_status, nullable=False),
        sa.Column("ledger_error", sa.Text(), nullable=True),
        sa.Column("ledger_committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("reviewed_by", sa.String(length=64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["performed_by"], ["users.username"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.username"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("ledger_tx_id"),
    )
    op.create_index("ix_asset_events_asset_id", "asset_events", ["asset_id"])
    op.create_index("ix_asset_events_document_hash", "asset_events", ["document_hash"])
    op.create_index("ix_asset_events_event_type", "asset_events", ["event_type"])
    op.create_index("ix_asset_events_ledger_status", "asset_events", ["ledger_status"])
    op.create_index("ix_asset_events_organization", "asset_events", ["organization"])
    op.create_index("ix_asset_events_performed_by", "asset_events", ["performed_by"])
    op.create_index("ix_asset_events_status", "asset_events", ["status"])

    op.create_table(
        "asset_documents",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.String(length=64), nullable=False),
        sa.Column("ledger_tx_id", sa.String(length=128), nullable=True),
        sa.Column("ledger_status", document_ledger_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["event_id"], ["asset_events.event_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.username"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("document_id"),
        sa.UniqueConstraint("event_id"),
        sa.UniqueConstraint("ledger_tx_id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_asset_documents_asset_id", "asset_documents", ["asset_id"])
    op.create_index("ix_asset_documents_event_id", "asset_documents", ["event_id"])
    op.create_index(
        "ix_asset_documents_ledger_status", "asset_documents", ["ledger_status"]
    )
    op.create_index("ix_asset_documents_sha256_hash", "asset_documents", ["sha256_hash"])
    op.create_index("ix_asset_documents_uploaded_by", "asset_documents", ["uploaded_by"])


def downgrade() -> None:
    op.drop_index("ix_asset_documents_uploaded_by", table_name="asset_documents")
    op.drop_index("ix_asset_documents_sha256_hash", table_name="asset_documents")
    op.drop_index("ix_asset_documents_ledger_status", table_name="asset_documents")
    op.drop_index("ix_asset_documents_event_id", table_name="asset_documents")
    op.drop_index("ix_asset_documents_asset_id", table_name="asset_documents")
    op.drop_table("asset_documents")

    op.drop_index("ix_asset_events_status", table_name="asset_events")
    op.drop_index("ix_asset_events_performed_by", table_name="asset_events")
    op.drop_index("ix_asset_events_organization", table_name="asset_events")
    op.drop_index("ix_asset_events_ledger_status", table_name="asset_events")
    op.drop_index("ix_asset_events_event_type", table_name="asset_events")
    op.drop_index("ix_asset_events_document_hash", table_name="asset_events")
    op.drop_index("ix_asset_events_asset_id", table_name="asset_events")
    op.drop_table("asset_events")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
