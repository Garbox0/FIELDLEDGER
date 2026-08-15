import os
from typing import Protocol

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import LedgerOutbox, LedgerStatus, User
from app.schemas import LedgerOperationRead


router = APIRouter(prefix="/ledger", tags=["ledger"])


def ledger_enabled() -> bool:
    return os.getenv("LEDGER_ENABLED", "false").lower() == "true"


def enqueue(
    db: Session,
    *,
    operation_id: str,
    aggregate_type: str,
    aggregate_id: str,
    action: str,
    organization: str,
    payload: dict[str, object],
) -> LedgerOutbox:
    item = LedgerOutbox(
        operation_id=operation_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        action=action,
        organization=organization,
        payload=payload,
        status=LedgerStatus.PENDING,
    )
    db.add(item)
    return item


class LedgerClient(Protocol):
    def ready(self) -> None: ...

    def document_by_hash(self, sha256_hash: str) -> dict[str, object]: ...


class HttpLedgerClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("FABRIC_GATEWAY_URL", "http://gateway:3000").rstrip("/")
        self.token = os.getenv("INTERNAL_GATEWAY_TOKEN", "")

    def headers(self) -> dict[str, str]:
        if len(self.token) < 32:
            raise RuntimeError("INTERNAL_GATEWAY_TOKEN must contain at least 32 characters")
        return {"Authorization": f"Bearer {self.token}"}

    def ready(self) -> None:
        response = httpx.get(f"{self.base_url}/ready", timeout=5)
        response.raise_for_status()

    def document_by_hash(self, sha256_hash: str) -> dict[str, object]:
        response = httpx.get(
            f"{self.base_url}/internal/ledger/documents/{sha256_hash}",
            headers=self.headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()


def get_ledger_client() -> LedgerClient:
    return HttpLedgerClient()


def verify_document_hash(client: LedgerClient, sha256_hash: str) -> dict[str, object]:
    if not ledger_enabled():
        raise HTTPException(status_code=503, detail="Ledger integration is disabled")
    try:
        return client.document_by_hash(sha256_hash)
    except (httpx.HTTPError, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail="Fabric verification failed") from exc


@router.get("/operations", response_model=list[LedgerOperationRead])
def list_operations(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[LedgerOutbox]:
    statement = select(LedgerOutbox).order_by(LedgerOutbox.created_at.desc()).limit(limit)
    return list(db.scalars(statement))
