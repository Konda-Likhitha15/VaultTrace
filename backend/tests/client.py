"""Test HTTP client using an in-process ASGI transport."""

import asyncio
from typing import Any

import httpx

from app.main import app


class InProcessClient:
    """Small synchronous facade over httpx's in-process ASGI transport."""

    def __init__(self) -> None:
        self.transport = httpx.ASGITransport(app=app)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send a request directly to FastAPI without opening a network port."""
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(transport=self.transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send an in-process GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send an in-process POST request."""
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send an in-process PATCH request."""
        return self.request("PATCH", url, **kwargs)
