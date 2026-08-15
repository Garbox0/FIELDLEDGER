import hashlib
from datetime import UTC, datetime, timedelta
import random
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets import get_asset_or_404
from app.auth import get_current_user, require_roles
from app.database import get_db
from app.ledger import enqueue
from app.models import (
    AppRole,
    LedgerStatus,
    Organization,
    TelemetryBatch,
    TelemetryReading,
    User,
)
from app.schemas import (
    TelemetryBatchRead,
    TelemetryBatchTrigger,
    TelemetryReadingCreate,
    TelemetryReadingRead,
    TelemetryVerifyRequest,
    TelemetryVerifyResponse,
)


router = APIRouter(tags=["telemetry"])


def compute_merkle_root(readings: list[TelemetryReading]) -> str:
    """Compute a canonical SHA-256 Merkle tree root for a list of telemetry readings."""
    if not readings:
        return hashlib.sha256(b"empty_telemetry_batch").hexdigest()

    # Step 1: Leaf hashes from canonical serialization
    leaf_hashes: list[bytes] = []
    for r in readings:
        ts_str = r.timestamp.isoformat() if r.timestamp else ""
        canonical_str = (
            f"{r.id}:{r.asset_id}:{ts_str}:"
            f"{r.pressure_psi or 0.0:.2f}:"
            f"{r.temperature_c or 0.0:.2f}:"
            f"{r.vibration_mms or 0.0:.2f}:"
            f"{r.flow_rate_bpd or 0.0:.2f}"
        )
        leaf_hashes.append(hashlib.sha256(canonical_str.encode("utf-8")).digest())

    # Step 2: Build tree layer by layer
    current_layer = leaf_hashes
    while len(current_layer) > 1:
        next_layer: list[bytes] = []
        for i in range(0, len(current_layer), 2):
            left = current_layer[i]
            right = current_layer[i + 1] if i + 1 < len(current_layer) else left
            combined = hashlib.sha256(left + right).digest()
            next_layer.append(combined)
        current_layer = next_layer

    return current_layer[0].hex()


@router.post(
    "/assets/{asset_id}/telemetry",
    response_model=TelemetryReadingRead,
    status_code=status.HTTP_201_CREATED,
)
def ingest_reading(
    asset_id: str,
    payload: TelemetryReadingCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(
        require_roles(AppRole.ADMIN, AppRole.OPERATOR, AppRole.CONTRACTOR)
    ),
) -> TelemetryReading:
    get_asset_or_404(asset_id, db)
    reading = TelemetryReading(
        asset_id=asset_id,
        timestamp=payload.timestamp or datetime.now(UTC),
        pressure_psi=payload.pressure_psi,
        temperature_c=payload.temperature_c,
        vibration_mms=payload.vibration_mms,
        flow_rate_bpd=payload.flow_rate_bpd,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


@router.get(
    "/assets/{asset_id}/telemetry",
    response_model=list[TelemetryReadingRead],
)
def list_readings(
    asset_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[TelemetryReading]:
    get_asset_or_404(asset_id, db)
    statement = (
        select(TelemetryReading)
        .where(TelemetryReading.asset_id == asset_id)
        .order_by(TelemetryReading.timestamp.desc(), TelemetryReading.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


@router.post(
    "/assets/{asset_id}/telemetry/simulate",
    response_model=list[TelemetryReadingRead],
    status_code=status.HTTP_201_CREATED,
)
def simulate_telemetry_stream(
    asset_id: str,
    count: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(
        require_roles(AppRole.ADMIN, AppRole.OPERATOR)
    ),
) -> list[TelemetryReading]:
    """Generates realistic synthetic sensor readings for Oil & Gas equipment demo."""
    get_asset_or_404(asset_id, db)
    base_time = datetime.now(UTC) - timedelta(minutes=count * 2)
    created: list[TelemetryReading] = []

    for i in range(count):
        reading_time = base_time + timedelta(minutes=i * 2)
        # Realistic variance for wellhead / compressor sensors
        pressure = round(random.gauss(1250.0, 35.0), 2)
        temperature = round(random.gauss(68.5, 4.2), 2)
        vibration = round(max(0.1, random.gauss(2.1, 0.4)), 2)
        flow_rate = round(random.gauss(480.0, 25.0), 2)

        reading = TelemetryReading(
            asset_id=asset_id,
            timestamp=reading_time,
            pressure_psi=pressure,
            temperature_c=temperature,
            vibration_mms=vibration,
            flow_rate_bpd=flow_rate,
        )
        db.add(reading)
        created.append(reading)

    db.commit()
    for r in created:
        db.refresh(r)
    return created


@router.post(
    "/assets/{asset_id}/telemetry/batch",
    response_model=TelemetryBatchRead,
    status_code=status.HTTP_201_CREATED,
)
def create_telemetry_batch_anchor(
    asset_id: str,
    payload: TelemetryBatchTrigger = TelemetryBatchTrigger(),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(AppRole.ADMIN, AppRole.OPERATOR)
    ),
) -> TelemetryBatch:
    """Groups unbatched sensor readings, computes the SHA-256 Merkle root, and anchors to Fabric."""
    get_asset_or_404(asset_id, db)
    organization = db.get(Organization, current_user.organization_id)
    if organization is None:
        raise HTTPException(status_code=409, detail="User organization is missing")

    statement = (
        select(TelemetryReading)
        .where(
            TelemetryReading.asset_id == asset_id,
            TelemetryReading.batch_id.is_(None),
        )
        .order_by(TelemetryReading.timestamp.asc(), TelemetryReading.id.asc())
        .limit(payload.max_readings)
    )
    unbatched = list(db.scalars(statement))
    if not unbatched:
        raise HTTPException(
            status_code=400,
            detail="No unbatched telemetry readings available to anchor",
        )

    batch_id = f"BATCH-{asset_id}-{uuid4().hex[:12].upper()}"
    merkle_root = compute_merkle_root(unbatched)
    period_start = unbatched[0].timestamp
    period_end = unbatched[-1].timestamp

    batch = TelemetryBatch(
        batch_id=batch_id,
        asset_id=asset_id,
        period_start=period_start,
        period_end=period_end,
        reading_count=len(unbatched),
        merkle_root=merkle_root,
        ledger_status=LedgerStatus.PENDING,
    )
    db.add(batch)

    # Link readings to this batch
    for r in unbatched:
        r.batch_id = batch_id

    # Enqueue to Fabric outbox
    enqueue(
        db,
        operation_id=f"telemetry:{batch_id}:register",
        aggregate_type="TELEMETRY_BATCH",
        aggregate_id=batch_id,
        action="REGISTER_TELEMETRY_BATCH",
        organization=organization.name,
        payload={
            "batchId": batch_id,
            "assetId": asset_id,
            "merkleRoot": merkle_root,
            "readingCount": len(unbatched),
            "periodStart": period_start.isoformat(),
            "periodEnd": period_end.isoformat(),
        },
    )

    db.commit()
    db.refresh(batch)
    return batch


@router.get(
    "/assets/{asset_id}/telemetry/batches",
    response_model=list[TelemetryBatchRead],
)
def list_telemetry_batches(
    asset_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[TelemetryBatch]:
    get_asset_or_404(asset_id, db)
    statement = (
        select(TelemetryBatch)
        .where(TelemetryBatch.asset_id == asset_id)
        .order_by(TelemetryBatch.period_start.desc())
    )
    return list(db.scalars(statement))


@router.post(
    "/telemetry/verify-batch",
    response_model=TelemetryVerifyResponse,
)
def verify_telemetry_batch(
    payload: TelemetryVerifyRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(
        require_roles(AppRole.ADMIN, AppRole.OPERATOR, AppRole.AUDITOR)
    ),
) -> TelemetryVerifyResponse:
    batch = db.get(TelemetryBatch, payload.batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Telemetry batch not found")

    readings = list(
        db.scalars(
            select(TelemetryReading)
            .where(TelemetryReading.batch_id == batch.batch_id)
            .order_by(TelemetryReading.timestamp.asc(), TelemetryReading.id.asc())
        )
    )

    computed = compute_merkle_root(readings)
    is_valid = computed == batch.merkle_root

    return TelemetryVerifyResponse(
        verified=is_valid,
        batch_id=batch.batch_id,
        merkle_root=batch.merkle_root,
        computed_merkle_root=computed,
        reading_count=len(readings),
        ledger_status=batch.ledger_status,
        ledger_tx_id=batch.ledger_tx_id,
        reason=None if is_valid else "MERKLE_ROOT_MISMATCH",
    )
