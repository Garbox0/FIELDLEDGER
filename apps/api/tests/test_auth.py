from fastapi.testclient import TestClient

from app import auth
from conftest import TEST_PASSWORD


def test_login_and_current_user(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "contractor", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    current = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert current.status_code == 200
    assert current.json() == {
        "username": "contractor",
        "role": "CONTRACTOR",
        "organization_id": "CONTRACTOR_ORG",
        "is_active": True,
    }


def test_bad_credentials_and_invalid_token_are_rejected(client: TestClient) -> None:
    bad_password = client.post(
        "/api/v1/auth/login",
        data={"username": "contractor", "password": "incorrect-password"},
    )
    assert bad_password.status_code == 401

    invalid_token = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert invalid_token.status_code == 401


def test_login_rate_limit_blocks_repeated_failures(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("LOGIN_RATE_LIMIT_ATTEMPTS", "2")
    auth._login_failures.clear()

    for _ in range(2):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "contractor", "password": "incorrect-password"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        data={"username": "contractor", "password": TEST_PASSWORD},
    )
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    auth._login_failures.clear()


def test_public_demo_login_is_read_only_and_configurable(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("PUBLIC_DEMO_VIEWER", "true")
    assert client.get("/api/v1/auth/demo").json() == {"enabled": True}

    login = client.post("/api/v1/auth/demo")
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/assets", headers=headers).status_code == 200
    assert client.post("/api/v1/assets", headers=headers, json={}).status_code == 403

    monkeypatch.setenv("PUBLIC_DEMO_VIEWER", "false")
    assert client.post("/api/v1/auth/demo").status_code == 404
