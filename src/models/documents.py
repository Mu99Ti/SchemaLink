"""Document models for SchemaLink hybrid indexing."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DatabaseDocument(BaseModel):
    document_id: str
    document_type: str = "database"
    database_id: str
    engine_type: str
    domains: list[str] = Field(default_factory=list)
    description: str
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_search_text(self) -> str:
        domain_str = ", ".join(self.domains) if self.domains else "general"
        return f"Database: {self.database_id} ({self.engine_type}). Domains: {domain_str}. Description: {self.description}"


class TableDocument(BaseModel):
    document_id: str
    document_type: str = "table"
    database_id: str
    schema_name: str | None = None
    table_name: str
    description: str
    business_terms: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    column_names: list[str] = Field(default_factory=list)
    primary_keys: list[str] = Field(default_factory=list)
    foreign_keys: list[dict[str, str]] = Field(default_factory=list)
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_search_text(self) -> str:
        terms = ", ".join(self.business_terms) if self.business_terms else ""
        cols = ", ".join(self.column_names)
        rules = " ".join(self.business_rules)
        return (
            f"Table: {self.table_name} in database {self.database_id}. "
            f"Description: {self.description}. "
            f"Synonyms and business terms: {terms}. "
            f"Columns: {cols}. "
            f"Business rules: {rules}"
        ).strip()


class ColumnDocument(BaseModel):
    document_id: str
    document_type: str = "column"
    database_id: str
    schema_name: str | None = None
    table_name: str
    column_name: str
    data_type: str
    is_primary_key: bool = False
    is_foreign_key: bool = False
    description: str
    business_terms: list[str] = Field(default_factory=list)
    categorical_values: list[str] = Field(default_factory=list)
    parent_table_description: str = ""
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_search_text(self) -> str:
        terms = ", ".join(self.business_terms) if self.business_terms else ""
        enums = ", ".join(self.categorical_values[:15]) if self.categorical_values else ""
        enum_part = f" Sample values / Enums: {enums}." if enums else ""
        return (
            f"Column: {self.column_name} ({self.data_type}) in table {self.table_name} ({self.database_id}). "
            f"Description: {self.description}. "
            f"Parent table: {self.parent_table_description}. "
            f"Terms: {terms}.{enum_part}"
        ).strip()


class ExemplarDocument(BaseModel):
    document_id: str
    document_type: str = "exemplar"
    database_id: str
    query: str
    approved_tables: list[str] = Field(default_factory=list)
    approved_columns: list[dict[str, str]] = Field(default_factory=list)
    approved_joins: list[dict[str, str]] = Field(default_factory=list)
    timestamp: str
    content_hash: str

    def to_search_text(self) -> str:
        return f"Exemplar query for database {self.database_id}: {self.query}"
