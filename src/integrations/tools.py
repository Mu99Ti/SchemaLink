"""Agent Framework Tools & Function Calling adapters for SchemaLink."""

from __future__ import annotations

from typing import Any

from src.engine import SchemaLink


def get_openai_tool_definition() -> dict[str, Any]:
    """Returns OpenAI / Anthropic compatible function calling schema for retrieve_schema."""
    return {
        "type": "function",
        "function": {
            "name": "retrieve_schema",
            "description": (
                "Retrieves relevant tables, columns, data types, and join paths for a natural language question. "
                "Call this tool before writing SQL to get the exact schema context and avoid hallucinations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The analytical user question, e.g. 'Show monthly revenue by branch in California'",
                    },
                    "database_id": {
                        "type": "string",
                        "description": "Optional specific database ID if known",
                    },
                },
                "required": ["query"],
            },
        },
    }


def create_langchain_tool(engine: SchemaLink):
    """Creates a LangChain / LangGraph compatible @tool wrapper."""
    try:
        from langchain_core.tools import tool

        @tool
        def retrieve_schema_tool(query: str, database_id: str | None = None) -> str:
            """Retrieve relevant tables, columns, and foreign keys for a database query."""
            context = engine.retrieve_sync(query=query, database_id=database_id)
            return context.to_prompt(format_type="compact_ddl")

        return retrieve_schema_tool
    except ImportError:
        # Fallback callable if langchain-core is not installed
        def retrieve_schema_tool(query: str, database_id: str | None = None) -> str:
            context = engine.retrieve_sync(query=query, database_id=database_id)
            return context.to_prompt(format_type="compact_ddl")

        return retrieve_schema_tool
