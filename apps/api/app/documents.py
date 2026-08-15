import hashlib
from pathlib import PurePath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.events import get_event_or_404
from app.ledger import LedgerClient, enqueue, get_ledger_client, verify_document_hash
from app.models import (
    AppRole,
    AssetDocument,
    DocumentCategory,
    EventStatus,
    LedgerStatus,
    Organization,
    User,
)
from app.schemas import DocumentRead, DocumentVerification
from app.storage import ObjectStorage, get_storage


router = APIRouter(tags=["documents"])
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_SIGNATURES = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


def validate_document(content: bytes, content_type: str) -> None:
    signatures = ALLOWED_SIGNATURES.get(content_type)
    if signatures is None:
        raise HTTPException(status_code=415, detail="Unsupported document type")
    if not content.startswith(signatures):
        raise HTTPException(
            status_code=422, detail="File signature does not match content type"
        )


def read_document(file: UploadFile) -> tuple[bytes, str]:
    content = file.file.read(MAX_DOCUMENT_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Document is empty")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds 10 MiB")
    content_type = file.content_type or "application/octet-stream"
    validate_document(content, content_type)
    return content, content_type


@router.post(
    "/events/{event_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    event_id: str,
    file: UploadFile = File(...),
    category: DocumentCategory = Form(default=DocumentCategory.OTHER),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            AppRole.ADMIN, AppRole.OPERATOR, AppRole.CONTRACTOR, AppRole.AUDITOR
        )
    ),
    storage: ObjectStorage = Depends(get_storage),
) -> AssetDocument:
    event = get_event_or_404(event_id, db)
    if event.status != EventStatus.PROPOSED:
        raise HTTPException(status_code=409, detail="Reviewed events cannot accept documents")

    content, content_type = read_document(file)
    filename = PurePath(file.filename or "").name.replace("\x00", "")
    if not filename or len(filename) > 255:
        raise HTTPException(status_code=422, detail="Invalid filename")

    document_id = str(uuid4())
    sha256_hash = hashlib.sha256(content).hexdigest()
    object_key = f"{event.asset_id}/{event.event_id}/{document_id}"
    document = AssetDocument(
        document_id=document_id,
        event_id=event.event_id,
        asset_id=event.asset_id,
        category=category,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        object_key=object_key,
        sha256_hash=sha256_hash,
        uploaded_by=current_user.username,
        notes=notes[:500] if notes else None,
        ledger_status=LedgerStatus.PENDING,
    )

    storage.put_bytes(object_key, content, content_type, sha256_hash)
    event.document_hash = sha256_hash
    event.ledger_status = LedgerStatus.PENDING
    db.add(document)
    organization = db.get(Organization, current_user.organization_id)
    if organization is None:
        storage.remove(object_key)
        raise HTTPException(status_code=409, detail="User organization is missing")
    enqueue(
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
            "category": document.category.value,
            "sha256Hash": document.sha256_hash,
            "contentType": document.content_type,
            "sizeBytes": document.size_bytes,
            "uploadedBy": document.uploaded_by,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        storage.remove(object_key)
        raise HTTPException(
            status_code=409, detail="Document could not be registered"
        ) from exc
    except Exception:
        db.rollback()
        storage.remove(object_key)
        raise
    db.refresh(document)
    return document


@router.get("/events/{event_id}/documents", response_model=list[DocumentRead])
def list_event_documents(
    event_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[AssetDocument]:
    get_event_or_404(event_id, db)
    statement = (
        select(AssetDocument)
        .where(AssetDocument.event_id == event_id)
        .order_by(AssetDocument.created_at.asc())
    )
    return list(db.scalars(statement))


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> AssetDocument:
    document = db.get(AssetDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/documents/verify", response_model=DocumentVerification)
def verify_document(
    file: UploadFile = File(...),
    _current_user: User = Depends(
        require_roles(AppRole.ADMIN, AppRole.OPERATOR, AppRole.AUDITOR)
    ),
    ledger: LedgerClient = Depends(get_ledger_client),
) -> DocumentVerification:
    content, _content_type = read_document(file)
    sha256_hash = hashlib.sha256(content).hexdigest()
    result = verify_document_hash(ledger, sha256_hash)
    if result.get("found") is not True:
        return DocumentVerification(
            verified=False, sha256_hash=sha256_hash, reason="HASH_NOT_REGISTERED"
        )
    document = result.get("document")
    if not isinstance(document, dict):
        raise HTTPException(status_code=502, detail="Fabric returned an invalid record")
    return DocumentVerification(
        verified=True,
        sha256_hash=sha256_hash,
        document=document,
    )

