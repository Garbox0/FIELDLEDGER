import os
import re
import time

import httpx
from sqlalchemy import select

from app.database import SessionLocal
from app.models import LedgerOutbox, LedgerStatus


BASE_URL = os.getenv("FIELDLEDGER_INTERNAL_URL", "http://api:8000")


def login(client: httpx.Client, username: str, password: str) -> dict[str, str]:
    response = client.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def demo_password(username: str) -> str:
    password = os.getenv(f"DEMO_{username.upper()}_PASSWORD") or os.getenv(
        "DEMO_PASSWORD", ""
    )
    if len(password) < 16:
        raise RuntimeError(f"password for demo user {username} is missing")
    return password


def wait_for_commit(operation_ids: list[str]) -> list[LedgerOutbox]:
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        with SessionLocal() as db:
            items = list(
                db.scalars(
                    select(LedgerOutbox)
                    .where(LedgerOutbox.operation_id.in_(operation_ids))
                    .order_by(LedgerOutbox.created_at)
                )
            )
            if len(items) == len(operation_ids) and all(
                item.status == LedgerStatus.COMMITTED for item in items
            ):
                return items
        time.sleep(2)
    raise RuntimeError("ledger operations did not commit within 240 seconds")


def main() -> None:
    suffix = f"{int(time.time()):X}"
    asset_id = f"E2E-{suffix}"
    event_id = f"EVT-E2E-{suffix}"
    pdf = f"%PDF-1.7\nFieldLedger E2E {suffix}\n%%EOF\n".encode()

    with httpx.Client(timeout=30) as client:
        operator = login(client, "operator", demo_password("operator"))
        contractor = login(client, "contractor", demo_password("contractor"))
        auditor = login(client, "auditor", demo_password("auditor"))

        response = client.post(
            f"{BASE_URL}/api/v1/assets",
            headers=operator,
            json={
                "asset_id": asset_id,
                "asset_type": "VALVE",
                "name": "Ledger end-to-end valve",
                "site": "Raspberry Pi acceptance test",
                "serial_number": suffix,
                "status": "ACTIVE",
                "criticality": "LOW",
            },
        )
        response.raise_for_status()
        response = client.post(
            f"{BASE_URL}/api/v1/assets/{asset_id}/maintenance",
            headers=contractor,
            json={
                "event_id": event_id,
                "event_type": "PREVENTIVE_MAINTENANCE",
                "description": "End-to-end Fabric transaction test.",
                "idempotency_key": f"e2e-{suffix}",
            },
        )
        response.raise_for_status()
        response = client.post(
            f"{BASE_URL}/api/v1/events/{event_id}/documents",
            headers=contractor,
            files={"file": ("evidence.pdf", pdf, "application/pdf")},
        )
        response.raise_for_status()
        document = response.json()
        response = client.post(
            f"{BASE_URL}/api/v1/events/{event_id}/approve",
            headers=operator,
            json={},
        )
        response.raise_for_status()

        operations = wait_for_commit(
            [
                f"asset:{asset_id}:create",
                f"event:{event_id}:propose",
                f"document:{document['document_id']}:register",
                f"event:{event_id}:review",
            ]
        )
        original = client.post(
            f"{BASE_URL}/api/v1/documents/verify",
            headers=auditor,
            files={"file": ("evidence.pdf", pdf, "application/pdf")},
        )
        original.raise_for_status()
        if original.json().get("verified") is not True:
            raise RuntimeError("original evidence was not verified")

        modified = client.post(
            f"{BASE_URL}/api/v1/documents/verify",
            headers=auditor,
            files={"file": ("evidence.pdf", pdf + b"modified", "application/pdf")},
        )
        modified.raise_for_status()
        if modified.json().get("verified") is not False:
            raise RuntimeError("modified evidence incorrectly verified")

    for item in operations:
        if not item.ledger_tx_id or not re.fullmatch(r"[a-f0-9]{64}", item.ledger_tx_id):
            raise RuntimeError(f"invalid transaction ID for {item.operation_id}")
    print(f"PASS asset={asset_id} event={event_id} document={document['document_id']}")
    print(f"PASS sha256={document['sha256_hash']} original=true modified=false")
    for item in operations:
        print(f"COMMITTED block={item.block_number} tx={item.ledger_tx_id} action={item.action}")


if __name__ == "__main__":
    main()
