"""Create the three built-in VaultTrace authorization roles."""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role

ROLE_NAMES = ("Administrator", "Owner", "Viewer")


def seed_roles() -> None:
    """Insert any missing built-in roles in one transaction."""
    with SessionLocal.begin() as session:
        existing = set(session.scalars(select(Role.name)).all())
        session.add_all(Role(name=name) for name in ROLE_NAMES if name not in existing)


if __name__ == "__main__":
    seed_roles()
    print("VaultTrace roles are seeded.")
