from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class AssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    DECOMMISSIONED = "DECOMMISSIONED"


class AssetCriticality(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class OrganizationType(StrEnum):
    OPERATOR = "OPERATOR"
    CONTRACTOR = "CONTRACTOR"
    AUDITOR = "AUDITOR"


class AppRole(StrEnum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    CONTRACTOR = "CONTRACTOR"
    AUDITOR = "AUDITOR"
    VIEWER = "VIEWER"


class AssetEventType(StrEnum):
    INSTALLATION = "INSTALLATION"
    INSPECTION = "INSPECTION"
    PREVENTIVE_MAINTENANCE = "PREVENTIVE_MAINTENANCE"
    CORRECTIVE_MAINTENANCE = "CORRECTIVE_MAINTENANCE"
    PART_REPLACEMENT = "PART_REPLACEMENT"
    PRESSURE_TEST = "PRESSURE_TEST"
    CALIBRATION = "CALIBRATION"
    CERTIFICATION = "CERTIFICATION"
    FAILURE = "FAILURE"
    RETURN_TO_SERVICE = "RETURN_TO_SERVICE"
    DECOMMISSION = "DECOMMISSION"


class DocumentCategory(StrEnum):
    WORK_ORDER = "WORK_ORDER"
    CALIBRATION_CERT = "CALIBRATION_CERT"
    INSPECTION_PHOTO = "INSPECTION_PHOTO"
    NDT_REPORT = "NDT_REPORT"
    LAB_ANALYSIS = "LAB_ANALYSIS"
    DECOMMISSION_RECORD = "DECOMMISSION_RECORD"
    OTHER = "OTHER"


class EventStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LedgerStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "organization_type IN ('OPERATOR', 'CONTRACTOR', 'AUDITOR')",
            name="organization_type",
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    organization_type: Mapped[OrganizationType] = mapped_column(
        SqlEnum(
            OrganizationType,
            name="organization_type",
            native_enum=False,
            validate_strings=True,
        )
    )
    fabric_msp_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('ADMIN', 'OPERATOR', 'CONTRACTOR', 'AUDITOR', 'VIEWER')",
            name="app_role",
        ),
    )

    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[AppRole] = mapped_column(
        SqlEnum(
            AppRole,
            name="app_role",
            native_enum=False,
            validate_strings=True,
        ),
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.organization_id", ondelete="RESTRICT"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'MAINTENANCE', 'OUT_OF_SERVICE', 'DECOMMISSIONED')",
            name="asset_status",
        ),
        CheckConstraint(
            "criticality IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="asset_criticality",
        ),
    )

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_type: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(160))
    site: Mapped[str] = mapped_column(String(160), index=True)
    location: Mapped[str | None] = mapped_column(String(160))
    manufacturer: Mapped[str | None] = mapped_column(String(160))
    serial_number: Mapped[str | None] = mapped_column(String(128), index=True)
    operator: Mapped[str | None] = mapped_column(String(160))
    installation_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[AssetStatus] = mapped_column(
        SqlEnum(
            AssetStatus,
            name="asset_status",
            native_enum=False,
            validate_strings=True,
        ),
        default=AssetStatus.ACTIVE,
        index=True,
    )
    criticality: Mapped[AssetCriticality] = mapped_column(
        SqlEnum(
            AssetCriticality,
            name="asset_criticality",
            native_enum=False,
            validate_strings=True,
        ),
        default=AssetCriticality.MEDIUM,
        index=True,
    )
    decommissioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decommission_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AssetEvent(Base):
    __tablename__ = "asset_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('INSTALLATION', 'INSPECTION', "
            "'PREVENTIVE_MAINTENANCE', 'CORRECTIVE_MAINTENANCE', "
            "'PART_REPLACEMENT', 'PRESSURE_TEST', 'CALIBRATION', "
            "'CERTIFICATION', 'FAILURE', 'RETURN_TO_SERVICE', 'DECOMMISSION')",
            name="asset_event_type",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'APPROVED', 'REJECTED')",
            name="event_status",
        ),
        CheckConstraint(
            "ledger_status IN ('PENDING', 'SUBMITTED', 'COMMITTED', 'FAILED')",
            name="ledger_status",
        ),
        UniqueConstraint("idempotency_key"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[AssetEventType] = mapped_column(
        SqlEnum(
            AssetEventType,
            name="asset_event_type",
            native_enum=False,
            validate_strings=True,
        ),
        index=True,
    )
    description: Mapped[str] = mapped_column(Text)
    organization: Mapped[str] = mapped_column(String(160), index=True)
    performed_by: Mapped[str] = mapped_column(
        ForeignKey("users.username", ondelete="RESTRICT"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    status: Mapped[EventStatus] = mapped_column(
        SqlEnum(
            EventStatus,
            name="event_status",
            native_enum=False,
            validate_strings=True,
        ),
        default=EventStatus.PROPOSED,
        index=True,
    )
    document_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    ledger_tx_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    ledger_status: Mapped[LedgerStatus] = mapped_column(
        SqlEnum(
            LedgerStatus,
            name="ledger_status",
            native_enum=False,
            validate_strings=True,
        ),
        default=LedgerStatus.PENDING,
        index=True,
    )
    ledger_error: Mapped[str | None] = mapped_column(Text)
    ledger_committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.username", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    documents: Mapped[list["AssetDocument"]] = relationship(
        "AssetDocument", back_populates="event", cascade="all, delete-orphan"
    )


class AssetDocument(Base):
    __tablename__ = "asset_documents"
    __table_args__ = (
        CheckConstraint(
            "category IN ('WORK_ORDER', 'CALIBRATION_CERT', 'INSPECTION_PHOTO', "
            "'NDT_REPORT', 'LAB_ANALYSIS', 'DECOMMISSION_RECORD', 'OTHER')",
            name="document_category",
        ),
        CheckConstraint(
            "ledger_status IN ('PENDING', 'SUBMITTED', 'COMMITTED', 'FAILED')",
            name="document_ledger_status",
        ),
        UniqueConstraint("object_key"),
    )

    document_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("asset_events.event_id", ondelete="RESTRICT"), index=True
    )
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="RESTRICT"), index=True
    )
    category: Mapped[DocumentCategory] = mapped_column(
        SqlEnum(
            DocumentCategory,
            name="document_category",
            native_enum=False,
            validate_strings=True,
        ),
        default=DocumentCategory.OTHER,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    object_key: Mapped[str] = mapped_column(String(512))
    sha256_hash: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by: Mapped[str] = mapped_column(
        ForeignKey("users.username", ondelete="RESTRICT"), index=True
    )
    notes: Mapped[str | None] = mapped_column(String(500))
    ledger_tx_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    ledger_status: Mapped[LedgerStatus] = mapped_column(
        SqlEnum(
            LedgerStatus,
            name="document_ledger_status",
            native_enum=False,
            validate_strings=True,
        ),
        default=LedgerStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    event: Mapped["AssetEvent"] = relationship("AssetEvent", back_populates="documents")


class LedgerOutbox(Base):
    __tablename__ = "ledger_outbox"
    __table_args__ = (
        CheckConstraint(
            "action IN ('REGISTER_ASSET', 'PROPOSE_EVENT', 'REVIEW_EVENT', "
            "'REGISTER_DOCUMENT', 'DECOMMISSION_ASSET', 'REGISTER_TELEMETRY_BATCH')",
            name="ledger_outbox_action",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SUBMITTED', 'COMMITTED', 'FAILED')",
            name="ledger_outbox_status",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(32), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    organization: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[LedgerStatus] = mapped_column(
        SqlEnum(
            LedgerStatus,
            name="ledger_outbox_status",
            native_enum=False,
            validate_strings=True,
        ),
        default=LedgerStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    ledger_tx_id: Mapped[str | None] = mapped_column(String(128), index=True)
    block_number: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TelemetryBatch(Base):
    __tablename__ = "telemetry_batches"
    __table_args__ = (
        CheckConstraint(
            "ledger_status IN ('PENDING', 'SUBMITTED', 'COMMITTED', 'FAILED')",
            name="batch_ledger_status",
        ),
    )

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="RESTRICT"), index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reading_count: Mapped[int] = mapped_column()
    merkle_root: Mapped[str] = mapped_column(String(64), index=True)
    ledger_tx_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    ledger_status: Mapped[LedgerStatus] = mapped_column(
        SqlEnum(
            LedgerStatus,
            name="batch_ledger_status",
            native_enum=False,
            validate_strings=True,
        ),
        default=LedgerStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TelemetryReading(Base):
    __tablename__ = "telemetry_readings"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_id", ondelete="RESTRICT"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    pressure_psi: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    vibration_mms: Mapped[float | None] = mapped_column(Float)
    flow_rate_bpd: Mapped[float | None] = mapped_column(Float)
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("telemetry_batches.batch_id", ondelete="SET NULL"), index=True
    )
