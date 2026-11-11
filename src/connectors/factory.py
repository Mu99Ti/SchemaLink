"""Connector factory for database drivers."""

from __future__ import annotations

from typing import Any

from src.connectors.base import BaseConnector, SQLAlchemyConnector


def create_connector(
    database_id: str,
    connection_uri: str,
    engine_type: str | None = None,
    options: dict[str, Any] | None = None,
) -> BaseConnector:
    """Creates an appropriate database connector based on the connection URI."""
    return SQLAlchemyConnector(
        database_id=database_id,
        connection_uri=connection_uri,
        options=options,
    )
