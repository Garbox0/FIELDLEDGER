import os

from sqlalchemy import select

from app.auth import get_password_hash, verify_password
from app.database import SessionLocal
from app.models import AppRole, Organization, OrganizationType, User


ORGANIZATIONS = (
    Organization(
        organization_id="OPERATOR_ORG",
        name="OperatorOrg",
        organization_type=OrganizationType.OPERATOR,
        fabric_msp_id="OperatorMSP",
    ),
    Organization(
        organization_id="CONTRACTOR_ORG",
        name="ContractorOrg",
        organization_type=OrganizationType.CONTRACTOR,
        fabric_msp_id="ContractorMSP",
    ),
    Organization(
        organization_id="AUDITOR_ORG",
        name="AuditorOrg",
        organization_type=OrganizationType.AUDITOR,
        fabric_msp_id="AuditorMSP",
    ),
)

DEMO_USERS = (
    ("admin", AppRole.ADMIN, "OPERATOR_ORG"),
    ("operator", AppRole.OPERATOR, "OPERATOR_ORG"),
    ("contractor", AppRole.CONTRACTOR, "CONTRACTOR_ORG"),
    ("auditor", AppRole.AUDITOR, "AUDITOR_ORG"),
    ("viewer", AppRole.VIEWER, "AUDITOR_ORG"),
)


def demo_password(username: str) -> str:
    password = os.getenv(f"DEMO_{username.upper()}_PASSWORD") or os.getenv(
        "DEMO_PASSWORD", ""
    )
    if len(password) < 16:
        raise RuntimeError(
            f"password for demo user {username} must contain 16 characters"
        )
    return password


def main() -> None:
    with SessionLocal() as db:
        existing_orgs = set(db.scalars(select(Organization.organization_id)))
        db.add_all(
            organization
            for organization in ORGANIZATIONS
            if organization.organization_id not in existing_orgs
        )
        db.commit()

        existing_users = {user.username: user for user in db.scalars(select(User))}
        for username, role, organization_id in DEMO_USERS:
            password = demo_password(username)
            user = existing_users.get(username)
            if user is None:
                db.add(
                    User(
                        username=username,
                        password_hash=get_password_hash(password),
                        role=role,
                        organization_id=organization_id,
                    )
                )
            elif not verify_password(password, user.password_hash):
                user.password_hash = get_password_hash(password)
        db.commit()

    print("Seeded demo identities: admin, operator, contractor, auditor, viewer")


if __name__ == "__main__":
    main()
