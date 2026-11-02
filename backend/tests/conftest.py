"""Isolated database fixtures for backend tests."""

import os
from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-signing-secret-not-for-production")

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Role
from backend.tests.client import InProcessClient
from backend.tests.database import TestSession, test_engine


@pytest.fixture()
def client() -> Generator[InProcessClient, None, None]:
    """Provide an API client with a fresh in-memory schema for each test."""
    Base.metadata.create_all(test_engine)
    with TestSession.begin() as session:
        session.add_all(Role(name=name) for name in ("Administrator", "Owner", "Viewer"))

    def override_get_db() -> Generator[Session, None, None]:
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield InProcessClient()
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(test_engine)
