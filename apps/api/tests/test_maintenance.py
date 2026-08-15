import hashlib

from fastapi.testclient import TestClient


def create_asset(client, auth_headers, payload) -> None:
    response = client.post(
        "/api/v1/assets", json=payload, headers=auth_headers("operator")
    )
    assert response.status_code == 201


def event_payload(event_id: str = "EVT-00042", key: str = "maintenance-00042") -> dict:
    return {
        "event_id": event_id,
        "event_type": "PREVENTIVE_MAINTENANCE",
        "description": "Replace the valve seal and perform a pressure test.",
        "idempotency_key": key,
    }


def test_maintenance_document_and_approval_flow(
    client: TestClient, auth_headers, asset_payload, fake_storage
) -> None:
    create_asset(client, auth_headers, asset_payload)
    contractor_headers = auth_headers("contractor")
    proposed = client.post(
        "/api/v1/assets/VALVE-VM-0042/maintenance",
        json=event_payload(),
        headers=contractor_headers,
    )
    assert proposed.status_code == 201
    assert proposed.json()["status"] == "PROPOSED"
    assert proposed.json()["ledger_status"] == "PENDING"
    assert proposed.json()["ledger_tx_id"] is None

    duplicate = client.post(
        "/api/v1/assets/VALVE-VM-0042/maintenance",
        json=event_payload("EVT-OTHER", "maintenance-00042"),
        headers=contractor_headers,
    )
    assert duplicate.status_code == 409

    own_approval = client.post(
        "/api/v1/events/EVT-00042/approve", json={}, headers=contractor_headers
    )
    assert own_approval.status_code == 403

    pdf = b"%PDF-1.7\nFieldLedger maintenance report\n%%EOF\n"
    uploaded = client.post(
        "/api/v1/events/EVT-00042/documents",
        data={"category": "WORK_ORDER", "notes": "Permiso de trabajo y orden de servicio"},
        files={"file": ("maintenance-report.pdf", pdf, "application/pdf")},
        headers=contractor_headers,
    )
    assert uploaded.status_code == 201
    metadata = uploaded.json()
    assert metadata["sha256_hash"] == hashlib.sha256(pdf).hexdigest()
    assert metadata["category"] == "WORK_ORDER"
    assert metadata["notes"] == "Permiso de trabajo y orden de servicio"
    assert metadata["ledger_status"] == "PENDING"
    assert list(fake_storage.objects.values()) == [pdf]

    # Test uploading second document to the SAME event (Multi-Document support 1:N)
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    uploaded_photo = client.post(
        "/api/v1/events/EVT-00042/documents",
        data={"category": "INSPECTION_PHOTO", "notes": "Foto de inspeccion previa"},
        files={"file": ("valve-inspection.png", png_bytes, "image/png")},
        headers=contractor_headers,
    )
    assert uploaded_photo.status_code == 201
    assert uploaded_photo.json()["category"] == "INSPECTION_PHOTO"

    # List all documents for this event
    docs_list = client.get(
        "/api/v1/events/EVT-00042/documents",
        headers=auth_headers("auditor"),
    )
    assert docs_list.status_code == 200
    assert len(docs_list.json()) == 2
    assert {d["category"] for d in docs_list.json()} == {"WORK_ORDER", "INSPECTION_PHOTO"}

    fetched = client.get(
        f"/api/v1/documents/{metadata['document_id']}",
        headers=auth_headers("auditor"),
    )
    assert fetched.status_code == 200
    assert fetched.json()["sha256_hash"] == metadata["sha256_hash"]

    approved = client.post(
        "/api/v1/events/EVT-00042/approve",
        json={},
        headers=auth_headers("operator"),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["reviewed_by"] == "operator"
    assert approved.json()["ledger_status"] == "PENDING"

    late_upload = client.post(
        "/api/v1/events/EVT-00042/documents",
        files={"file": ("late.pdf", pdf, "application/pdf")},
        headers=contractor_headers,
    )
    assert late_upload.status_code == 409

    timeline = client.get(
        "/api/v1/assets/VALVE-VM-0042/events", headers=auth_headers("viewer")
    )
    assert timeline.status_code == 200
    assert [item["event_id"] for item in timeline.json()] == ["EVT-00042"]


def test_rejection_requires_reason(client, auth_headers, asset_payload) -> None:
    create_asset(client, auth_headers, asset_payload)
    proposed = client.post(
        "/api/v1/assets/VALVE-VM-0042/maintenance",
        json=event_payload("EVT-REJECT", "maintenance-reject-0001"),
        headers=auth_headers("contractor"),
    )
    assert proposed.status_code == 201

    missing_reason = client.post(
        "/api/v1/events/EVT-REJECT/reject",
        json={},
        headers=auth_headers("operator"),
    )
    assert missing_reason.status_code == 422

    rejected = client.post(
        "/api/v1/events/EVT-REJECT/reject",
        json={"reason": "Pressure-test evidence is incomplete."},
        headers=auth_headers("operator"),
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["ledger_status"] == "PENDING"


def test_document_type_and_signature_are_validated(
    client, auth_headers, asset_payload
) -> None:
    create_asset(client, auth_headers, asset_payload)
    contractor = auth_headers("contractor")
    client.post(
        "/api/v1/assets/VALVE-VM-0042/maintenance",
        json=event_payload(),
        headers=contractor,
    )

    text_file = client.post(
        "/api/v1/events/EVT-00042/documents",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
        headers=contractor,
    )
    assert text_file.status_code == 415

    fake_pdf = client.post(
        "/api/v1/events/EVT-00042/documents",
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        headers=contractor,
    )
    assert fake_pdf.status_code == 422
