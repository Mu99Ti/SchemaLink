"""Categorical value profiler for low-cardinality enum discovery."""

from __future__ import annotations

import logging

from src.catalog.models import ColumnProfile, DatabaseInfo
from src.connectors.base import BaseConnector

logger = logging.getLogger(__name__)


class CategoricalProfiler:
    """Discovers and profiles low-cardinality columns (enums, statuses, categories)."""

    def __init__(self, connector: BaseConnector, max_distinct: int = 50):
        self.connector = connector
        self.max_distinct = max_distinct

    def profile_database(self, db_info: DatabaseInfo) -> dict[str, ColumnProfile]:
        """Profiles columns across all tables, returning a map of 'table.column' -> ColumnProfile."""
        profiles: dict[str, ColumnProfile] = {}

        candidate_type_substrings = [
            "char",
            "varchar",
            "text",
            "string",
            "enum",
            "int",
            "smallint",
            "bool",
        ]

        for table in db_info.tables:
            for col in table.columns:
                type_lower = col.data_type.lower()
                # Skip primary keys, blobs, timestamps, floats
                if col.is_primary_key or any(skip in type_lower for skip in ["blob", "bytea", "binary", "json", "xml"]):
                    continue

                if any(sub in type_lower for sub in candidate_type_substrings):
                    vals = self.connector.sample_distinct_values(
                        table.table_name, col.name, limit=self.max_distinct + 1
                    )
                    # If distinct count is <= max_distinct, it's a valid categorical column
                    if 1 <= len(vals) <= self.max_distinct:
                        key = f"{table.table_name}.{col.name}"
                        profiles[key] = ColumnProfile(
                            database_id=db_info.database_id,
                            table_name=table.table_name,
                            column_name=col.name,
                            cardinality=len(vals),
                            distinct_values=vals,
                            sample_values=vals[:10],
                        )

        return profiles
