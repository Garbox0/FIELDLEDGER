def test_web_ui_is_served_with_security_headers(client) -> None:
    response = client.get("/app/")

    assert response.status_code == 200
    assert "FieldLedger" in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"


def test_ledger_operations_require_login(client) -> None:
    assert client.get("/api/v1/ledger/operations").status_code == 401
