import hashlib

from app.database import get_db
from app.ledger import get_ledger_client
from app.main import app
from app.models import LedgerOutbox


def test_mutations_enqueue_ordered_ledger_operations(
    client, auth_headers, asset_payload
) -> None:
    assert client.post(
        "/api/v1/assets", json=asset_payload, headers=auth_headers("operator")
    ).status_code == 201
    assert client.post(
        "/api/v1/assets/VALVE-VM-0042/maintenance",
        json={
            "event_id": "EVT-LEDGER-1",
            "event_type": "PREVENTIVE_MAINTENANCE",
            "description": "Verify outbox ordering.",
            "idempotency_key": "ledger-operation-1",
        },
        headers=auth_headers("contractor"),
    ).status_code == 201

    pdf = b"%PDF-1.7\nledger test\n%%EOF\n"
    uploaded = client.post(
        "/api/v1/events/EVT-LEDGER-1/documents",
        files={"file": ("evidence.pdf", pdf, "application/pdf")},
        headers=auth_headers("contractor"),
    )
    assert uploaded.status_code == 201
    assert client.post(
        "/api/v1/events/EVT-LEDGER-1/approve",
        json={},
        headers=auth_headers("operator"),
    ).status_code == 200

    override = app.dependency_overrides[get_db]()
    db = next(override)
    try:
        operations = db.query(LedgerOutbox).order_by(LedgerOutbox.created_at).all()
        assert [item.action for item in operations] == [
            "REGISTER_ASSET",
            "PROPOSE_EVENT",
            "REGISTER_DOCUMENT",
            "REVIEW_EVENT",
        ]
        assert [item.organization for item in operations] == [
            "OperatorOrg",
            "ContractorOrg",
            "ContractorOrg",
            "OperatorOrg",
        ]
    finally:
        override.close()


def test_document_verification_queries_the_ledger(
    client, auth_headers, monkeypatch
) -> None:
    pdf = b"%PDF-1.7\noriginal evidence\n%%EOF\n"
    sha256_hash = hashlib.sha256(pdf).hexdigest()

    class FakeLedger:
        def ready(self) -> None:
            pass

        def document_by_hash(self, requested_hash: str) -> dict[str, object]:
            assert requested_hash == sha256_hash
            return {
                "found": True,
                "document": {
                    "sha256Hash": requested_hash,
                    "ledgerTxId": "real-looking-test-fixture",
                },
            }

    monkeypatch.setenv("LEDGER_ENABLED", "true")
    app.dependency_overrides[get_ledger_client] = lambda: FakeLedger()
    try:
        response = client.post(
            "/api/v1/documents/verify",
            files={"file": ("evidence.pdf", pdf, "application/pdf")},
            headers=auth_headers("auditor"),
        )
    finally:
        app.dependency_overrides.pop(get_ledger_client, None)

    assert response.status_code == 200
    assert response.json()["verified"] is True
    assert response.json()["sha256_hash"] == sha256_hash
