from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.ledger import enqueue
from app.models import (
    AppRole,
    Asset,
    AssetDocument,
    AssetEvent,
    AssetEventType,
    AssetStatus,
    EventStatus,
    LedgerOutbox,
    LedgerStatus,
    Organization,
    TelemetryBatch,
    User,
)
from app.schemas import (
    AssetCreate,
    AssetDecommissionRequest,
    AssetRead,
    AssetTimelineItem,
    AssetTimelineResponse,
    AssetUpdate,
)


router = APIRouter(prefix="/assets", tags=["assets"])


def get_asset_or_404(asset_id: str, db: Session) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(AppRole.ADMIN, AppRole.OPERATOR)),
) -> Asset:
    asset = Asset(**payload.model_dump())
    organization = db.get(Organization, current_user.organization_id)
    if organization is None:
        raise HTTPException(status_code=409, detail="User organization is missing")
    db.add(asset)
    enqueue(
        db,
        operation_id=f"asset:{asset.asset_id}:create",
        aggregate_type="ASSET",
        aggregate_id=asset.asset_id,
        action="REGISTER_ASSET",
        organization=organization.name,
        payload={
            "assetId": asset.asset_id,
            "assetType": asset.asset_type,
            "name": asset.name,
            "site": asset.site,
            "serialNumber": asset.serial_number,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Asset already exists") from exc
    db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetRead])
def list_assets(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[Asset]:
    statement = select(Asset).order_by(Asset.asset_id).offset(offset).limit(limit)
    return list(db.scalars(statement))


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Asset:
    return get_asset_or_404(asset_id, db)


@router.patch("/{asset_id}", response_model=AssetRead)
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(AppRole.ADMIN, AppRole.OPERATOR)),
) -> Asset:
    asset = get_asset_or_404(asset_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    asset.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(AppRole.ADMIN, AppRole.OPERATOR)),
) -> Response:
    db.delete(get_asset_or_404(asset_id, db))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Assets with events cannot be deleted"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{asset_id}/decommission", response_model=AssetRead)
def decommission_asset(
    asset_id: str,
    payload: AssetDecommissionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(AppRole.ADMIN, AppRole.OPERATOR)),
) -> Asset:
    asset = get_asset_or_404(asset_id, db)
    if asset.status == AssetStatus.DECOMMISSIONED:
        raise HTTPException(
            status_code=409, detail="Asset is already decommissioned"
        )

    organization = db.get(Organization, current_user.organization_id)
    if organization is None:
        raise HTTPException(status_code=409, detail="User organization is missing")

    now = datetime.now(UTC)
    asset.status = AssetStatus.DECOMMISSIONED
    asset.decommissioned_at = now
    asset.decommission_reason = payload.reason
    asset.updated_at = now

    # Create auditable decommission event
    decom_event = AssetEvent(
        event_id=f"EVT-DECOM-{asset.asset_id}",
        asset_id=asset.asset_id,
        event_type=AssetEventType.DECOMMISSION,
        description=f"Baja y desafectación formal del activo: {payload.reason}",
        organization=organization.name,
        performed_by=current_user.username,
        timestamp=now,
        status=EventStatus.APPROVED,
        ledger_status=LedgerStatus.PENDING,
        idempotency_key=f"decom:{asset.asset_id}:{now.timestamp()}",
        reviewed_by=current_user.username,
        reviewed_at=now,
    )
    db.add(decom_event)

    enqueue(
        db,
        operation_id=f"asset:{asset.asset_id}:decommission",
        aggregate_type="ASSET",
        aggregate_id=asset.asset_id,
        action="DECOMMISSION_ASSET",
        organization=organization.name,
        payload={
            "assetId": asset.asset_id,
            "reason": payload.reason,
            "decommissionedBy": current_user.username,
            "decommissionedAt": now.isoformat(),
        },
    )

    db.commit()
    db.refresh(asset)
    return asset


@router.get("/{asset_id}/timeline", response_model=AssetTimelineResponse)
def get_asset_timeline(
    asset_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> AssetTimelineResponse:
    asset = get_asset_or_404(asset_id, db)
    timeline_items: list[AssetTimelineItem] = []

    # 1. Asset Creation
    creation_op = db.scalar(
        select(LedgerOutbox).where(
            LedgerOutbox.aggregate_type == "ASSET",
            LedgerOutbox.aggregate_id == asset.asset_id,
            LedgerOutbox.action == "REGISTER_ASSET",
        )
    )
    timeline_items.append(
        AssetTimelineItem(
            item_id=f"creation-{asset.asset_id}",
            item_type="CREATION",
            title=f"Alta de Activo: {asset.name}",
            description=f"Activo tipo {asset.asset_type} dado de alta en yacimiento {asset.site}.",
            organization=creation_op.organization if creation_op else "OperatorOrg",
            author=asset.operator or "admin",
            timestamp=asset.created_at,
            status=asset.status.value,
            ledger_tx_id=creation_op.ledger_tx_id if creation_op else None,
            block_number=creation_op.block_number if creation_op else None,
            details={
                "serialNumber": asset.serial_number or "N/A",
                "site": asset.site,
                "criticality": asset.criticality.value,
            },
        )
    )

    # 2. Events & Reviews & Documents
    events = list(
        db.scalars(
            select(AssetEvent)
            .where(AssetEvent.asset_id == asset.asset_id)
            .order_by(AssetEvent.timestamp.asc())
        )
    )
    for event in events:
        event_op = db.scalar(
            select(LedgerOutbox).where(
                LedgerOutbox.aggregate_type == "EVENT",
                LedgerOutbox.aggregate_id == event.event_id,
                LedgerOutbox.action == "PROPOSE_EVENT",
            )
        )
        timeline_items.append(
            AssetTimelineItem(
                item_id=f"event-{event.event_id}",
                item_type="EVENT",
                title=f"Mantenimiento: {event.event_type.value}",
                description=event.description,
                organization=event.organization,
                author=event.performed_by,
                timestamp=event.timestamp,
                status=event.status.value,
                ledger_tx_id=event_op.ledger_tx_id if event_op else event.ledger_tx_id,
                block_number=event_op.block_number if event_op else None,
                document_hash=event.document_hash,
                details={"eventId": event.event_id, "eventType": event.event_type.value},
            )
        )

        # Attached documents
        docs = list(
            db.scalars(
                select(AssetDocument)
                .where(AssetDocument.event_id == event.event_id)
                .order_by(AssetDocument.created_at.asc())
            )
        )
        for doc in docs:
            doc_op = db.scalar(
                select(LedgerOutbox).where(
                    LedgerOutbox.aggregate_type == "DOCUMENT",
                    LedgerOutbox.aggregate_id == doc.document_id,
                )
            )
            timeline_items.append(
                AssetTimelineItem(
                    item_id=f"doc-{doc.document_id}",
                    item_type="DOCUMENT",
                    title=f"Evidencia: {doc.category.value} ({doc.original_filename})",
                    description=f"Archivo {doc.content_type} ({round(doc.size_bytes / 1024, 1)} KB). Notas: {doc.notes or 'Sin notas'}",
                    organization=event.organization,
                    author=doc.uploaded_by,
                    timestamp=doc.created_at,
                    status=doc.ledger_status.value,
                    ledger_tx_id=doc_op.ledger_tx_id if doc_op else doc.ledger_tx_id,
                    block_number=doc_op.block_number if doc_op else None,
                    document_hash=doc.sha256_hash,
                    details={
                        "documentId": doc.document_id,
                        "filename": doc.original_filename,
                        "category": doc.category.value,
                        "sizeBytes": doc.size_bytes,
                    },
                )
            )

        # Event review
        if event.status in (EventStatus.APPROVED, EventStatus.REJECTED) and event.reviewed_by:
            review_op = db.scalar(
                select(LedgerOutbox).where(
                    LedgerOutbox.aggregate_type == "EVENT",
                    LedgerOutbox.aggregate_id == event.event_id,
                    LedgerOutbox.action == "REVIEW_EVENT",
                )
            )
            timeline_items.append(
                AssetTimelineItem(
                    item_id=f"review-{event.event_id}",
                    item_type="REVIEW",
                    title=f"Revisión: {event.status.value}",
                    description=f"Revisado por {event.reviewed_by}. " + (
                        f"Motivo de rechazo: {event.rejection_reason}"
                        if event.rejection_reason
                        else "Intervención aprobada conforme a estándares."
                    ),
                    organization="OperatorOrg",
                    author=event.reviewed_by,
                    timestamp=event.reviewed_at or event.timestamp,
                    status=event.status.value,
                    ledger_tx_id=review_op.ledger_tx_id if review_op else None,
                    block_number=review_op.block_number if review_op else None,
                    details={"eventId": event.event_id, "decision": event.status.value},
                )
            )

    # 3. Telemetry Batches
    batches = list(
        db.scalars(
            select(TelemetryBatch)
            .where(TelemetryBatch.asset_id == asset.asset_id)
            .order_by(TelemetryBatch.period_start.asc())
        )
    )
    for batch in batches:
        timeline_items.append(
            AssetTimelineItem(
                item_id=f"telemetry-{batch.batch_id}",
                item_type="TELEMETRY_BATCH",
                title=f"Lote de Telemetría IoT ({batch.reading_count} lecturas)",
                description=f"Período: {batch.period_start.strftime('%Y-%m-%d %H:%M')} a {batch.period_end.strftime('%H:%M')}. Merkle Root anclado en Fabric.",
                organization="OperatorOrg",
                author="sensor-gateway",
                timestamp=batch.created_at,
                status=batch.ledger_status.value,
                ledger_tx_id=batch.ledger_tx_id,
                document_hash=batch.merkle_root,
                details={
                    "batchId": batch.batch_id,
                    "readingCount": batch.reading_count,
                    "merkleRoot": batch.merkle_root,
                },
            )
        )

    # Sort all timeline items chronologically
    timeline_items.sort(key=lambda item: item.timestamp)

    return AssetTimelineResponse(
        asset_id=asset.asset_id,
        asset_name=asset.name,
        timeline=timeline_items,
    )

