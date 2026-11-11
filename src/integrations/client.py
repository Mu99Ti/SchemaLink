"""SchemaLink Python SDK Client."""

from __future__ import annotations

import httpx

from src.models.context import CuratedSchemaContext


class SchemaLinkClient:
    """Client for communicating with a remote or local SchemaLink REST API."""

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def retrieve_schema(
        self,
        query: str,
        database_id: str | None = None,
        mode: str = "autonomous",
    ) -> CuratedSchemaContext:
        """Retrieves curated schema context for a natural language query."""
        url = f"{self.base_url}/api/v1/retrieval/schema"
        payload = {"query": query, "database_id": database_id, "mode": mode}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return CuratedSchemaContext(**data)
