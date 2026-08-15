from sqlalchemy import select

from app.database import SessionLocal
from app.ledger import enqueue
from app.models import Asset, AssetDocument, AssetEvent, EventStatus, LedgerOutbox, Organization, User


def add_if_missing(db, **values) -> int:
    if db.get(LedgerOutbox, values["operation_id"]) is not None:
        return 0
    enqueue(db, **values)
    db.flush()
    return 1


def main() -> None:
    created = 0
    with SessionLocal.begin() as db:
        for asset in db.scalars(select(Asset).order_by(Asset.created_at, Asset.asset_id)):
            created += add_if_missing(
                db,
                operation_id=f"asset:{asset.asset_id}:create",
                aggregate_type="ASSET",
                aggregate_id=asset.asset_id,
                action="REGISTER_ASSET",
                organization="OperatorOrg",
                payload={
                    "assetId": asset.asset_id,
                    "assetType": asset.asset_type,
                    "name": asset.name,
                    "site": asset.site,
                    "serialNumber": asset.serial_number,
                },
            )

        events = db.scalars(select(AssetEvent).order_by(AssetEvent.created_at, AssetEvent.event_id))
        for event in events:
            created += add_if_missing(
                db,
                operation_id=f"event:{event.event_id}:propose",
                aggregate_type="EVENT",
                aggregate_id=event.event_id,
                action="PROPOSE_EVENT",
                organization=event.organization,
                payload={
                    "eventId": event.event_id,
                    "assetId": event.asset_id,
                    "eventType": event.event_type.value,
                    "description": event.description,
                    "performedBy": event.performed_by,
                    "performedAt": event.timestamp.isoformat(),
                },
            )
            document = db.scalar(select(AssetDocument).where(AssetDocument.event_id == event.event_id))
            if document is not None:
                user = db.get(User, document.uploaded_by)
                organization = db.get(Organization, user.organization_id) if user else None
                if organization is None:
                    raise RuntimeError(f"organization missing for {document.uploaded_by}")
                created += add_if_missing(
                    db,
                    operation_id=f"document:{document.document_id}:register",
                    aggregate_type="DOCUMENT",
                    aggregate_id=document.document_id,
                    action="REGISTER_DOCUMENT",
                    organization=organization.name,
                    payload={
                        "documentId": document.document_id,
                        "eventId": document.event_id,
                        "assetId": document.asset_id,
                        "sha256Hash": document.sha256_hash,
                        "contentType": document.content_type,
                        "sizeBytes": document.size_bytes,
                        "uploadedBy": document.uploaded_by,
                    },
                )
            if event.status in (EventStatus.APPROVED, EventStatus.REJECTED):
                reviewer = db.get(User, event.reviewed_by) if event.reviewed_by else None
                organization = db.get(Organization, reviewer.organization_id) if reviewer else None
                if organization is None:
                    raise RuntimeError(f"reviewer organization missing for {event.event_id}")
                created += add_if_missing(
                    db,
                    operation_id=f"event:{event.event_id}:review",
                    aggregate_type="EVENT",
                    aggregate_id=event.event_id,
                    action="REVIEW_EVENT",
                    organization=organization.name,
                    payload={
                        "eventId": event.event_id,
                        "decision": event.status.value,
                        "reviewedBy": event.reviewed_by,
                        "reason": event.rejection_reason,
                    },
                )
    print(f"Ledger reconciliation complete: {created} operation(s) enqueued")


if __name__ == "__main__":
    main()
