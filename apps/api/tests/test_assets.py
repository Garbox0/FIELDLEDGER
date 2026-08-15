from fastapi.testclient import TestClient

from app.main import app
from app.storage import get_storage


def test_asset_crud(client, auth_headers, asset_payload: dict[str, object]) -> None:
    headers = auth_headers("admin")
    created = client.post("/api/v1/assets", json=asset_payload, headers=headers)
    assert created.status_code == 201
    assert created.json()["asset_id"] == "VALVE-VM-0042"

    listed = client.get("/api/v1/assets", headers=headers)
    assert listed.status_code == 200
    assert [asset["asset_id"] for asset in listed.json()] == ["VALVE-VM-0042"]

    updated = client.patch(
        "/api/v1/assets/VALVE-VM-0042",
        json={"status": "MAINTENANCE", "criticality": "CRITICAL"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "MAINTENANCE"
    assert updated.json()["criticality"] == "CRITICAL"

    fetched = client.get("/api/v1/assets/VALVE-VM-0042", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Wellhead Safety Valve"

    deleted = client.delete("/api/v1/assets/VALVE-VM-0042", headers=headers)
    assert deleted.status_code == 204
    assert (
        client.get("/api/v1/assets/VALVE-VM-0042", headers=headers).status_code == 404
    )


def test_duplicate_asset_is_rejected(
    client: TestClient, auth_headers, asset_payload: dict[str, object]
) -> None:
    headers = auth_headers("operator")
    assert (
        client.post("/api/v1/assets", json=asset_payload, headers=headers).status_code
        == 201
    )
    duplicate = client.post("/api/v1/assets", json=asset_payload, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Asset already exists"}


def test_invalid_asset_is_rejected(
    client: TestClient, auth_headers, asset_payload: dict[str, object]
) -> None:
    headers = auth_headers("admin")
    asset_payload["criticality"] = "EXTREME"
    response = client.post("/api/v1/assets", json=asset_payload, headers=headers)
    assert response.status_code == 422

    null_required = client.patch(
        "/api/v1/assets/VALVE-VM-0042", json={"status": None}, headers=headers
    )
    assert null_required.status_code == 422


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_readiness_fails_when_object_storage_is_unavailable(
    client: TestClient,
) -> None:
    class UnavailableStorage:
        def ensure_bucket(self) -> None:
            raise OSError("object storage unavailable")

    app.dependency_overrides[get_storage] = lambda: UnavailableStorage()
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_assets_require_auth_and_viewer_cannot_create(
    client: TestClient, auth_headers, asset_payload: dict[str, object]
) -> None:
    assert client.get("/api/v1/assets").status_code == 401
    denied = client.post(
        "/api/v1/assets", json=asset_payload, headers=auth_headers("viewer")
    )
    assert denied.status_code == 403


def test_asset_decommission_flow(
    client: TestClient, auth_headers, asset_payload: dict[str, object]
) -> None:
    headers = auth_headers("operator")
    created = client.post("/api/v1/assets", json=asset_payload, headers=headers)
    assert created.status_code == 201

    # Decommission asset
    reason = "Agotamiento de reservorio y desmantelamiento de linea de inyeccion."
    decom = client.post(
        "/api/v1/assets/VALVE-VM-0042/decommission",
        json={"reason": reason},
        headers=headers,
    )
    assert decom.status_code == 200
    assert decom.json()["status"] == "DECOMMISSIONED"
    assert decom.json()["decommission_reason"] == reason
    assert decom.json()["decommissioned_at"] is not None

    # Cannot decommission twice
    decom_again = client.post(
        "/api/v1/assets/VALVE-VM-0042/decommission",
        json={"reason": "Otra razon"},
        headers=headers,
    )
    assert decom_again.status_code == 409


def test_asset_timeline(
    client: TestClient, auth_headers, asset_payload: dict[str, object]
) -> None:
    op_headers = auth_headers("operator")
    client.post("/api/v1/assets", json=asset_payload, headers=op_headers)

    # Propose maintenance
    client.post(
        "/api/v1/assets/VALVE-VM-0042/maintenance",
        json={
            "event_id": "EVT-TIMELINE-01",
            "event_type": "INSPECTION",
            "description": "Inspeccion de espesor por ultrasonido",
            "idempotency_key": "idemp-tl-01",
        },
        headers=auth_headers("contractor"),
    )

    timeline_res = client.get(
        "/api/v1/assets/VALVE-VM-0042/timeline",
        headers=auth_headers("auditor"),
    )
    assert timeline_res.status_code == 200
    data = timeline_res.json()
    assert data["asset_id"] == "VALVE-VM-0042"
    assert len(data["timeline"]) >= 2
    types = [item["item_type"] for item in data["timeline"]]
    assert "CREATION" in types
    assert "EVENT" in types

