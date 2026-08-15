from fastapi.testclient import TestClient

from app.models import TelemetryReading
from app.telemetry import compute_merkle_root


def create_asset(client: TestClient, auth_headers, payload: dict) -> None:
    client.post(
        "/api/v1/assets", json=payload, headers=auth_headers("operator")
    )


def test_merkle_root_computation_is_deterministic() -> None:
    r1 = TelemetryReading(
        id=1,
        asset_id="WELL-01",
        pressure_psi=1200.5,
        temperature_c=65.2,
        vibration_mms=2.1,
        flow_rate_bpd=450.0,
    )
    r2 = TelemetryReading(
        id=2,
        asset_id="WELL-01",
        pressure_psi=1205.0,
        temperature_c=65.8,
        vibration_mms=2.2,
        flow_rate_bpd=452.0,
    )
    root1 = compute_merkle_root([r1, r2])
    root2 = compute_merkle_root([r1, r2])
    assert root1 == root2
    assert len(root1) == 64

    # Tampering one reading changes the root
    r2_tampered = TelemetryReading(
        id=2,
        asset_id="WELL-01",
        pressure_psi=1999.0,  # tampered
        temperature_c=65.8,
        vibration_mms=2.2,
        flow_rate_bpd=452.0,
    )
    root_tampered = compute_merkle_root([r1, r2_tampered])
    assert root_tampered != root1


def test_telemetry_ingestion_and_simulation(
    client: TestClient, auth_headers, asset_payload: dict
) -> None:
    create_asset(client, auth_headers, asset_payload)
    op_headers = auth_headers("operator")

    # Ingest single reading
    ingested = client.post(
        "/api/v1/assets/VALVE-VM-0042/telemetry",
        json={
            "pressure_psi": 1250.0,
            "temperature_c": 68.0,
            "vibration_mms": 2.3,
            "flow_rate_bpd": 490.0,
        },
        headers=op_headers,
    )
    assert ingested.status_code == 201
    assert ingested.json()["pressure_psi"] == 1250.0

    # Simulate 15 readings
    simulated = client.post(
        "/api/v1/assets/VALVE-VM-0042/telemetry/simulate?count=15",
        headers=op_headers,
    )
    assert simulated.status_code == 201
    assert len(simulated.json()) == 15

    # Query readings
    readings = client.get(
        "/api/v1/assets/VALVE-VM-0042/telemetry",
        headers=auth_headers("viewer"),
    )
    assert readings.status_code == 200
    assert len(readings.json()) == 16


def test_telemetry_batch_creation_and_verification(
    client: TestClient, auth_headers, asset_payload: dict
) -> None:
    create_asset(client, auth_headers, asset_payload)
    op_headers = auth_headers("operator")

    # Simulate readings
    client.post(
        "/api/v1/assets/VALVE-VM-0042/telemetry/simulate?count=10",
        headers=op_headers,
    )

    # Trigger batch anchor to Fabric
    batch_res = client.post(
        "/api/v1/assets/VALVE-VM-0042/telemetry/batch",
        json={"max_readings": 50},
        headers=op_headers,
    )
    assert batch_res.status_code == 201
    batch_data = batch_res.json()
    assert batch_data["reading_count"] == 10
    assert len(batch_data["merkle_root"]) == 64
    assert batch_data["ledger_status"] == "PENDING"

    # Verify batch
    verify_res = client.post(
        "/api/v1/telemetry/verify-batch",
        json={"batch_id": batch_data["batch_id"]},
        headers=auth_headers("auditor"),
    )
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["verified"] is True
    assert verify_data["computed_merkle_root"] == batch_data["merkle_root"]

    # List batches
    batches_list = client.get(
        "/api/v1/assets/VALVE-VM-0042/telemetry/batches",
        headers=auth_headers("auditor"),
    )
    assert batches_list.status_code == 200
    assert len(batches_list.json()) == 1
