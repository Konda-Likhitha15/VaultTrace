"""Password creation policy shared by account creation and reset flows."""

import re


def validate_new_password(password: str) -> None:
    """Raise a safe validation error when a new password misses a rule."""
    requirements = (
        (len(password) >= 12, "at least 12 characters"),
        (re.search(r"[A-Z]", password) is not None, "an uppercase letter"),
        (re.search(r"[a-z]", password) is not None, "a lowercase letter"),
        (re.search(r"[0-9]", password) is not None, "a number"),
        (re.search(r"[^A-Za-z0-9]", password) is not None, "a special character"),
    )
    missing = [description for valid, description in requirements if not valid]
    if missing:
        raise ValueError("Password must contain " + ", ".join(missing) + ".")
