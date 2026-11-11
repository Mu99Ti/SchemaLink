"""Model Context Protocol (MCP) server for SchemaLink."""

from __future__ import annotations

import logging

from src.engine import SchemaLink

logger = logging.getLogger(__name__)


def create_mcp_server(engine: SchemaLink):
    """Creates an MCP server instance exposing `retrieve_schema`."""
    try:
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("SchemaLink")

        @mcp.tool()
        async def retrieve_schema(
            query: str,
            database_id: str | None = None,
            format: str = "compact_ddl",
        ) -> str:
            """
            Retrieves minimal, high-precision database schema (tables, columns, types, join paths)
            for a natural language question. Prevents hallucinations and token overflow.
            """
            context = await engine.retrieve(query=query, database_id=database_id)
            if format == "compact_ddl":
                return context.to_prompt("compact_ddl")
            return context.model_dump_json(indent=2)

        return mcp
    except ImportError:
        logger.warning("mcp library not installed. Install with `pip install mcp`.")
        return None
