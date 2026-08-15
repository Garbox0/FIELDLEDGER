import os
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import or_, select

from app.database import SessionLocal
from app.models import AssetDocument, AssetEvent, LedgerOutbox, LedgerStatus


GATEWAY_URL = os.getenv("FABRIC_GATEWAY_URL", "http://gateway:3000").rstrip("/")
TOKEN = os.getenv("INTERNAL_GATEWAY_TOKEN", "")


def next_item() -> str | None:
    now = datetime.now(UTC)
    stale = now - timedelta(minutes=2)
    with SessionLocal.begin() as db:
        statement = (
            select(LedgerOutbox)
            .where(
                or_(
                    LedgerOutbox.status.in_([LedgerStatus.PENDING, LedgerStatus.FAILED]),
                    (LedgerOutbox.status == LedgerStatus.SUBMITTED)
                    & (LedgerOutbox.updated_at < stale),
                ),
                LedgerOutbox.next_attempt_at <= now,
            )
            .order_by(LedgerOutbox.created_at, LedgerOutbox.operation_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        item = db.scalar(statement)
        if item is None:
            return None
        item.status = LedgerStatus.SUBMITTED
        item.attempts += 1
        item.updated_at = now
        return item.operation_id


def submit(operation_id: str) -> None:
    with SessionLocal() as db:
        item = db.get(LedgerOutbox, operation_id)
        if item is None:
            return
        request = {
            "operationId": item.operation_id,
            "organization": item.organization,
            "action": item.action,
            "payload": item.payload,
        }
        aggregate_type = item.aggregate_type
        aggregate_id = item.aggregate_id

    try:
        response = httpx.post(
            f"{GATEWAY_URL}/internal/ledger/submit",
            json=request,
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        tx_id = str(result["transactionId"])
        block_number = str(result["blockNumber"])
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        with SessionLocal.begin() as db:
            item = db.get(LedgerOutbox, operation_id)
            if item is None:
                return
            item.status = LedgerStatus.FAILED
            item.last_error = str(exc)[:2000]
            item.updated_at = datetime.now(UTC)
            item.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=min(300, 2 ** min(item.attempts, 8))
            )
            update_aggregate(
                db,
                operation_id,
                aggregate_type,
                aggregate_id,
                LedgerStatus.FAILED,
                error=item.last_error,
            )
        return

    with SessionLocal.begin() as db:
        item = db.get(LedgerOutbox, operation_id)
        if item is None:
            return
        item.status = LedgerStatus.COMMITTED
        item.ledger_tx_id = tx_id
        item.block_number = block_number
        item.last_error = None
        item.updated_at = datetime.now(UTC)
        update_aggregate(
            db,
            operation_id,
            aggregate_type,
            aggregate_id,
            LedgerStatus.COMMITTED,
            tx_id=tx_id,
        )


def update_aggregate(
    db,
    operation_id: str,
    aggregate_type: str,
    aggregate_id: str,
    status: LedgerStatus,
    *,
    tx_id: str | None = None,
    error: str | None = None,
) -> None:
    latest_operation = db.scalar(
        select(LedgerOutbox.operation_id)
        .where(
            LedgerOutbox.aggregate_type == aggregate_type,
            LedgerOutbox.aggregate_id == aggregate_id,
        )
        .order_by(LedgerOutbox.created_at.desc(), LedgerOutbox.operation_id.desc())
        .limit(1)
    )
    if latest_operation != operation_id:
        return
    record = (
        db.get(AssetEvent, aggregate_id)
        if aggregate_type == "EVENT"
        else db.get(AssetDocument, aggregate_id)
        if aggregate_type == "DOCUMENT"
        else None
    )
    if record is None:
        return
    record.ledger_status = status
    if hasattr(record, "ledger_error"):
        record.ledger_error = error
        record.ledger_committed_at = datetime.now(UTC) if status == LedgerStatus.COMMITTED else None
    if tx_id:
        record.ledger_tx_id = tx_id


def main() -> None:
    if len(TOKEN) < 32:
        raise RuntimeError("INTERNAL_GATEWAY_TOKEN must contain at least 32 characters")
    while True:
        operation_id = next_item()
        if operation_id is None:
            time.sleep(2)
        else:
            submit(operation_id)


if __name__ == "__main__":
    main()
