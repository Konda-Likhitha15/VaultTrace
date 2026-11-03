"""VaultTrace FastAPI application entry point."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
database_logger = logging.getLogger("vaulttrace.database")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Return a safe, actionable response without exposing database details."""
    database_logger.error("Database request failed (%s)", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database operation failed. Check PostgreSQL connectivity and retry."},
    )


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Return a minimal process health response."""
    return {"status": "ok"}
