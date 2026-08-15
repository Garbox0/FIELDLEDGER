import os

from sqlalchemy import select

from app.auth import get_password_hash
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


def main() -> None:
    password = os.getenv("DEMO_PASSWORD", "")
    if len(password) < 16:
        raise RuntimeError("DEMO_PASSWORD must contain at least 16 characters")

    with SessionLocal() as db:
        existing_orgs = set(db.scalars(select(Organization.organization_id)))
        db.add_all(
            organization
            for organization in ORGANIZATIONS
            if organization.organization_id not in existing_orgs
        )
        db.commit()

        existing_users = set(db.scalars(select(User.username)))
        for username, role, organization_id in DEMO_USERS:
            if username not in existing_users:
                db.add(
                    User(
                        username=username,
                        password_hash=get_password_hash(password),
                        role=role,
                        organization_id=organization_id,
                    )
                )
        db.commit()

    print("Seeded demo identities: admin, operator, contractor, auditor, viewer")


if __name__ == "__main__":
    main()
