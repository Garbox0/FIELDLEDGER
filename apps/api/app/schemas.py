from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    AppRole,
    AssetCriticality,
    AssetEventType,
    AssetStatus,
    DocumentCategory,
    EventStatus,
    LedgerStatus,
)


class AssetFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    asset_type: str = Field(min_length=2, max_length=64, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=160)
    site: str = Field(min_length=2, max_length=160)
    location: str | None = Field(default=None, max_length=160)
    manufacturer: str | None = Field(default=None, max_length=160)
    serial_number: str | None = Field(default=None, max_length=128)
    operator: str | None = Field(default=None, max_length=160)
    installation_date: date | None = None
    status: AssetStatus = AssetStatus.ACTIVE
    criticality: AssetCriticality = AssetCriticality.MEDIUM


class AssetCreate(AssetFields):
    asset_id: str = Field(
        min_length=3, max_length=64, pattern=r"^[A-Z0-9][A-Z0-9_-]+$"
    )


class AssetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    asset_type: str | None = Field(
        default=None, min_length=2, max_length=64, pattern=r"^[A-Z0-9_-]+$"
    )
    name: str | None = Field(default=None, min_length=2, max_length=160)
    site: str | None = Field(default=None, min_length=2, max_length=160)
    location: str | None = Field(default=None, max_length=160)
    manufacturer: str | None = Field(default=None, max_length=160)
    serial_number: str | None = Field(default=None, max_length=128)
    operator: str | None = Field(default=None, max_length=160)
    installation_date: date | None = None
    status: AssetStatus | None = None
    criticality: AssetCriticality | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        required = {"asset_type", "name", "site", "status", "criticality"}
        null_fields = required & self.model_fields_set
        if any(getattr(self, field) is None for field in null_fields):
            raise ValueError("required asset fields cannot be null")
        return self


class AssetDecommissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=5, max_length=2000)


class AssetRead(AssetFields):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    decommissioned_at: datetime | None = None
    decommission_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    role: AppRole
    organization_id: str
    is_active: bool


class MaintenanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_id: str = Field(
        min_length=3, max_length=64, pattern=r"^[A-Z0-9][A-Z0-9_-]+$"
    )
    event_type: AssetEventType
    description: str = Field(min_length=3, max_length=4000)
    timestamp: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_maintenance_type(self):
        allowed = {
            AssetEventType.PREVENTIVE_MAINTENANCE,
            AssetEventType.CORRECTIVE_MAINTENANCE,
            AssetEventType.PART_REPLACEMENT,
            AssetEventType.INSPECTION,
            AssetEventType.PRESSURE_TEST,
            AssetEventType.CALIBRATION,
            AssetEventType.CERTIFICATION,
        }
        if self.event_type not in allowed:
            raise ValueError("event_type is not a valid maintenance operation")
        return self


class EventReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str | None = Field(default=None, min_length=3, max_length=2000)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str
    event_id: str
    asset_id: str
    category: DocumentCategory
    original_filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    uploaded_by: str
    notes: str | None = None
    ledger_tx_id: str | None
    ledger_status: LedgerStatus
    created_at: datetime


class AssetEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    asset_id: str
    event_type: AssetEventType
    description: str
    organization: str
    performed_by: str
    timestamp: datetime
    status: EventStatus
    document_hash: str | None
    ledger_tx_id: str | None
    ledger_status: LedgerStatus
    ledger_error: str | None
    ledger_committed_at: datetime | None
    idempotency_key: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    documents: list[DocumentRead] = []


class DocumentVerification(BaseModel):
    verified: bool
    sha256_hash: str
    reason: str | None = None
    document: dict[str, object] | None = None


class AssetTimelineItem(BaseModel):
    item_id: str
    item_type: str  # "CREATION", "EVENT", "REVIEW", "DOCUMENT", "DECOMMISSION", "TELEMETRY_BATCH"
    title: str
    description: str
    organization: str
    author: str
    timestamp: datetime
    status: str
    ledger_tx_id: str | None = None
    block_number: str | None = None
    document_hash: str | None = None
    details: dict[str, object] = {}


class AssetTimelineResponse(BaseModel):
    asset_id: str
    asset_name: str
    timeline: list[AssetTimelineItem]


class TelemetryReadingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime | None = None
    pressure_psi: float | None = Field(default=None, ge=0, le=20000)
    temperature_c: float | None = Field(default=None, ge=-50, le=500)
    vibration_mms: float | None = Field(default=None, ge=0, le=100)
    flow_rate_bpd: float | None = Field(default=None, ge=0, le=50000)


class TelemetryReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: str
    timestamp: datetime
    pressure_psi: float | None
    temperature_c: float | None
    vibration_mms: float | None
    flow_rate_bpd: float | None
    batch_id: str | None


class TelemetryBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: str
    asset_id: str
    period_start: datetime
    period_end: datetime
    reading_count: int
    merkle_root: str
    ledger_tx_id: str | None
    ledger_status: LedgerStatus
    created_at: datetime


class TelemetryBatchTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_readings: int = Field(default=100, ge=1, le=1000)


class TelemetryVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str


class TelemetryVerifyResponse(BaseModel):
    verified: bool
    batch_id: str
    merkle_root: str
    computed_merkle_root: str
    reading_count: int
    ledger_status: LedgerStatus
    ledger_tx_id: str | None
    reason: str | None = None


class LedgerOperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operation_id: str
    aggregate_type: str
    aggregate_id: str
    action: str
    organization: str
    status: LedgerStatus
    attempts: int
    ledger_tx_id: str | None
    block_number: str | None
    created_at: datetime
    updated_at: datetime

