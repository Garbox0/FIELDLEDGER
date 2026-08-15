from fastapi.testclient import TestClient

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
