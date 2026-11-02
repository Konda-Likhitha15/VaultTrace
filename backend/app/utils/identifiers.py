"""Identifier utility placeholders."""

from uuid import UUID


def parse_uuid(value: str) -> UUID:
    """Parse a canonical UUID string."""
    return UUID(value)
