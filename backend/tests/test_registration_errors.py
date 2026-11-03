"""Ensure signup only reports actual duplicate-key failures as conflicts."""

from sqlalchemy.exc import IntegrityError

from app.services.registrations import _is_unique_constraint_violation


class PostgresDriverError(Exception):
    """Minimal psycopg-shaped error for SQLSTATE classification tests."""

    def __init__(self, message: str, sqlstate: str):
        super().__init__(message)
        self.sqlstate = sqlstate


def test_postgres_unique_violation_is_classified_as_duplicate() -> None:
    error = IntegrityError("INSERT", {}, PostgresDriverError("duplicate key", "23505"))
    assert _is_unique_constraint_violation(error)


def test_non_unique_postgres_integrity_failure_is_not_called_duplicate() -> None:
    error = IntegrityError("INSERT", {}, PostgresDriverError("not null violation", "23502"))
    assert not _is_unique_constraint_violation(error)


def test_sqlite_unique_failure_is_classified_as_duplicate() -> None:
    error = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: users.email"))
    assert _is_unique_constraint_violation(error)
