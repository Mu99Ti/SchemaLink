"""Base and SQLAlchemy database connectors for automated schema introspection."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from src.catalog.models import (
    ColumnInfo,
    DatabaseInfo,
    ForeignKeyInfo,
    TableInfo,
)

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """Abstract base connector for database metadata extraction."""

    def __init__(self, database_id: str, connection_uri: str, options: dict[str, Any] | None = None):
        self.database_id = database_id
        self.connection_uri = connection_uri
        self.options = options or {}

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify database connectivity."""
        pass

    @abstractmethod
    def introspect(self, schema_name: str | None = None) -> DatabaseInfo:
        """Extract full database metadata."""
        pass

    @abstractmethod
    def sample_distinct_values(self, table_name: str, column_name: str, limit: int = 50) -> list[str]:
        """Sample distinct values for low-cardinality categorical profiling."""
        pass


class SQLAlchemyConnector(BaseConnector):
    """Generic SQLAlchemy database connector supporting PostgreSQL, MySQL, SQLite, MSSQL, etc."""

    def __init__(self, database_id: str, connection_uri: str, options: dict[str, Any] | None = None):
        super().__init__(database_id, connection_uri, options)
        self.engine: Engine = create_engine(self.connection_uri, **self.options.get("engine_args", {}))

    def test_connection(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("Connection test failed for database %s: %s", self.database_id, e)
            return False

    def introspect(self, schema_name: str | None = None) -> DatabaseInfo:
        inspector = inspect(self.engine)
        engine_type = self.engine.dialect.name
        database_name = getattr(self.engine.url, "database", self.database_id) or self.database_id

        # Determine target schema if not provided
        target_schema = schema_name or getattr(inspector, "default_schema_name", None)

        tables: list[TableInfo] = []
        table_names = inspector.get_table_names(schema=target_schema)
        view_names = inspector.get_view_names(schema=target_schema)

        all_table_entries = [(t, "table") for t in table_names] + [(v, "view") for v in view_names]

        for name, t_type in all_table_entries:
            try:
                # Primary Keys
                pk_constraint = inspector.get_pk_constraint(name, schema=target_schema)
                pk_cols = set(pk_constraint.get("constrained_columns", []) if pk_constraint else [])

                # Foreign Keys
                fks_raw = inspector.get_foreign_keys(name, schema=target_schema) or []
                foreign_keys: list[ForeignKeyInfo] = []
                fk_col_names = set()
                for fk in fks_raw:
                    referred_table = fk.get("referred_table", "")
                    constrained_cols = fk.get("constrained_columns", [])
                    referred_cols = fk.get("referred_columns", [])
                    for s_col, t_col in zip(constrained_cols, referred_cols, strict=False):
                        fk_col_names.add(s_col)
                        foreign_keys.append(
                            ForeignKeyInfo(
                                source_column=s_col,
                                target_table=referred_table,
                                target_column=t_col,
                                relationship_type="physical_foreign_key",
                                confidence=1.0,
                            )
                        )

                # Columns
                raw_cols = inspector.get_columns(name, schema=target_schema)
                columns: list[ColumnInfo] = []
                for c in raw_cols:
                    col_name = c["name"]
                    data_type = str(c.get("type", "UNKNOWN"))
                    is_pk = col_name in pk_cols
                    is_fk = col_name in fk_col_names
                    comment = c.get("comment")

                    columns.append(
                        ColumnInfo(
                            name=col_name,
                            data_type=data_type,
                            nullable=c.get("nullable", True),
                            is_primary_key=is_pk,
                            is_foreign_key=is_fk,
                            default=str(c.get("default")) if c.get("default") is not None else None,
                            comment=comment,
                        )
                    )

                # Table comment
                table_comment = None
                try:
                    t_comment_obj = inspector.get_table_comment(name, schema=target_schema)
                    if isinstance(t_comment_obj, dict):
                        table_comment = t_comment_obj.get("text")
                    elif isinstance(t_comment_obj, str):
                        table_comment = t_comment_obj
                except Exception:
                    pass

                tables.append(
                    TableInfo(
                        table_name=name,
                        schema_name=target_schema,
                        table_type=t_type,
                        columns=columns,
                        foreign_keys=foreign_keys,
                        primary_key_columns=list(pk_cols),
                        comment=table_comment,
                    )
                )
            except Exception as e:
                logger.warning("Could not introspect table %s: %s", name, e)

        return DatabaseInfo(
            database_id=self.database_id,
            engine_type=engine_type,
            database_name=database_name,
            schema_name=target_schema,
            tables=tables,
        )

    def sample_distinct_values(self, table_name: str, column_name: str, limit: int = 50) -> list[str]:
        """Safely samples distinct values from a column."""
        # Sanitize identifiers
        clean_table = table_name.replace('"', "").replace("'", "").replace(";", "")
        clean_col = column_name.replace('"', "").replace("'", "").replace(";", "")

        query = text(
            f'SELECT DISTINCT "{clean_col}" FROM "{clean_table}" '
            f'WHERE "{clean_col}" IS NOT NULL LIMIT {int(limit)}'
        )
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query)
                values = [str(row[0]) for row in result.fetchall() if row[0] is not None]
                return values
        except Exception:
            # Fallback for dialects without quote support (e.g. standard SQLite without quotes)
            try:
                fallback_query = text(
                    f"SELECT DISTINCT {clean_col} FROM {clean_table} "
                    f"WHERE {clean_col} IS NOT NULL LIMIT {int(limit)}"
                )
                with self.engine.connect() as conn:
                    result = conn.execute(fallback_query)
                    values = [str(row[0]) for row in result.fetchall() if row[0] is not None]
                    return values
            except Exception as e:
                logger.debug("Distinct sampling failed for %s.%s: %s", clean_table, clean_col, e)
                return []
