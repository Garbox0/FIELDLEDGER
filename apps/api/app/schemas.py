from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    AppRole,
    AssetCriticality,
    AssetEventType,
    AssetStatus,
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


class AssetRead(AssetFields):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
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
        }
        if self.event_type not in allowed:
            raise ValueError("event_type is not a maintenance operation")
        return self


class EventReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str | None = Field(default=None, min_length=3, max_length=2000)


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


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str
    event_id: str
    asset_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    uploaded_by: str
    ledger_tx_id: str | None
    ledger_status: LedgerStatus
    created_at: datetime


class DocumentVerification(BaseModel):
    verified: bool
    sha256_hash: str
    reason: str | None = None
    document: dict[str, object] | None = None
