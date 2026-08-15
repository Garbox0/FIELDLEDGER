import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-only-secret-that-is-longer-than-thirty-two-characters")

from app.auth import get_password_hash
from app.database import Base, get_db
from app.main import app
from app.models import AppRole, Organization, OrganizationType, User
from app.storage import get_storage


TEST_PASSWORD = "correct-test-password"
TEST_PASSWORD_HASH = get_password_hash(TEST_PASSWORD)


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def ensure_bucket(self) -> None:
        pass

    def put_bytes(
        self, object_key: str, content: bytes, content_type: str, sha256_hash: str
    ) -> None:
        self.objects[object_key] = content

    def remove(self, object_key: str) -> None:
        self.objects.pop(object_key, None)


@pytest.fixture
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def client(fake_storage: FakeStorage) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with testing_session() as session:
        session.add_all(
            [
                Organization(
                    organization_id="OPERATOR_ORG",
                    name="OperatorOrg",
                    organization_type=OrganizationType.OPERATOR,
                ),
                Organization(
                    organization_id="CONTRACTOR_ORG",
                    name="ContractorOrg",
                    organization_type=OrganizationType.CONTRACTOR,
                ),
                Organization(
                    organization_id="AUDITOR_ORG",
                    name="AuditorOrg",
                    organization_type=OrganizationType.AUDITOR,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                User(
                    username="admin",
                    password_hash=TEST_PASSWORD_HASH,
                    role=AppRole.ADMIN,
                    organization_id="OPERATOR_ORG",
                ),
                User(
                    username="operator",
                    password_hash=TEST_PASSWORD_HASH,
                    role=AppRole.OPERATOR,
                    organization_id="OPERATOR_ORG",
                ),
                User(
                    username="contractor",
                    password_hash=TEST_PASSWORD_HASH,
                    role=AppRole.CONTRACTOR,
                    organization_id="CONTRACTOR_ORG",
                ),
                User(
                    username="auditor",
                    password_hash=TEST_PASSWORD_HASH,
                    role=AppRole.AUDITOR,
                    organization_id="AUDITOR_ORG",
                ),
                User(
                    username="viewer",
                    password_hash=TEST_PASSWORD_HASH,
                    role=AppRole.VIEWER,
                    organization_id="AUDITOR_ORG",
                ),
            ]
        )
        session.commit()

    def override_db():
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage] = lambda: fake_storage
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def auth_headers(client: TestClient):
    def login(username: str) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return login


@pytest.fixture
def asset_payload() -> dict[str, object]:
    return {
        "asset_id": "VALVE-VM-0042",
        "asset_type": "VALVE",
        "name": "Wellhead Safety Valve",
        "site": "Vaca Muerta Demo Field",
        "location": "WELL-137",
        "manufacturer": "Demo Industries",
        "serial_number": "SN-883721",
        "operator": "OperatorOrg",
        "installation_date": "2026-06-15",
        "status": "ACTIVE",
        "criticality": "HIGH",
    }
