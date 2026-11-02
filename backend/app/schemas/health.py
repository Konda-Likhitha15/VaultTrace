"""Health response schema."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Basic service health status."""

    status: str
