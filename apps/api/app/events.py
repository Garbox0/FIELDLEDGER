from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assets import get_asset_or_404
from app.auth import get_current_user, require_roles
from app.database import get_db
from app.ledger import enqueue
from app.models import AppRole, AssetEvent, EventStatus, LedgerStatus, Organization, User
from app.schemas import AssetEventRead, EventReview, MaintenanceCreate


router = APIRouter(tags=["events"])


def get_event_or_404(event_id: str, db: Session) -> AssetEvent:
    event = db.get(AssetEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post(
    "/assets/{asset_id}/maintenance",
    response_model=AssetEventRead,
    status_code=status.HTTP_201_CREATED,
)
def propose_maintenance(
    asset_id: str,
    payload: MaintenanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(AppRole.CONTRACTOR)
    ),
) -> AssetEvent:
    get_asset_or_404(asset_id, db)
    organization = db.get(Organization, current_user.organization_id)
    if organization is None:
        raise HTTPException(status_code=409, detail="User organization is missing")

    event = AssetEvent(
        event_id=payload.event_id,
        asset_id=asset_id,
        event_type=payload.event_type,
        description=payload.description,
        organization=organization.name,
        performed_by=current_user.username,
        timestamp=payload.timestamp or datetime.now(UTC),
        status=EventStatus.PROPOSED,
        ledger_status=LedgerStatus.PENDING,
        idempotency_key=payload.idempotency_key,
    )
    db.add(event)
    enqueue(
        db,
        operation_id=f"event:{event.event_id}:propose",
        aggregate_type="EVENT",
        aggregate_id=event.event_id,
        action="PROPOSE_EVENT",
        organization=organization.name,
        payload={
            "eventId": event.event_id,
            "assetId": event.asset_id,
            "eventType": event.event_type.value,
            "description": event.description,
            "performedBy": event.performed_by,
            "performedAt": event.timestamp.isoformat(),
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Event or idempotency key already exists"
        ) from exc
    db.refresh(event)
    return event


@router.get("/assets/{asset_id}/events", response_model=list[AssetEventRead])
def list_asset_events(
    asset_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[AssetEvent]:
    get_asset_or_404(asset_id, db)
    statement = (
        select(AssetEvent)
        .where(AssetEvent.asset_id == asset_id)
        .order_by(AssetEvent.timestamp, AssetEvent.event_id)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


@router.get("/events/{event_id}", response_model=AssetEventRead)
def get_event(
    event_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> AssetEvent:
    return get_event_or_404(event_id, db)


def review_event(
    event_id: str,
    new_status: EventStatus,
    payload: EventReview,
    db: Session,
    current_user: User,
) -> AssetEvent:
    event = get_event_or_404(event_id, db)
    if event.status != EventStatus.PROPOSED:
        raise HTTPException(status_code=409, detail="Event has already been reviewed")
    if event.performed_by == current_user.username:
        raise HTTPException(status_code=403, detail="Users cannot review their own work")
    if new_status == EventStatus.REJECTED and payload.reason is None:
        raise HTTPException(status_code=422, detail="A rejection reason is required")

    event.status = new_status
    event.reviewed_by = current_user.username
    event.reviewed_at = datetime.now(UTC)
    event.rejection_reason = payload.reason if new_status == EventStatus.REJECTED else None
    event.ledger_status = LedgerStatus.PENDING
    event.ledger_tx_id = None
    event.ledger_error = None
    event.ledger_committed_at = None
    organization = db.get(Organization, current_user.organization_id)
    if organization is None:
        raise HTTPException(status_code=409, detail="User organization is missing")
    enqueue(
        db,
        operation_id=f"event:{event.event_id}:review",
        aggregate_type="EVENT",
        aggregate_id=event.event_id,
        action="REVIEW_EVENT",
        organization=organization.name,
        payload={
            "eventId": event.event_id,
            "decision": new_status.value,
            "reviewedBy": current_user.username,
            "reason": event.rejection_reason,
        },
    )
    db.commit()
    db.refresh(event)
    return event


@router.post("/events/{event_id}/approve", response_model=AssetEventRead)
def approve_event(
    event_id: str,
    payload: EventReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(AppRole.OPERATOR, AppRole.ADMIN)),
) -> AssetEvent:
    return review_event(event_id, EventStatus.APPROVED, payload, db, current_user)


@router.post("/events/{event_id}/reject", response_model=AssetEventRead)
def reject_event(
    event_id: str,
    payload: EventReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(AppRole.OPERATOR, AppRole.ADMIN)),
) -> AssetEvent:
    return review_event(event_id, EventStatus.REJECTED, payload, db, current_user)
