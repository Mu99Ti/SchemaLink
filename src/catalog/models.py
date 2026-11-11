"""Schema metadata data models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    default: str | None = None
    comment: str | None = None


class ForeignKeyInfo(BaseModel):
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str = Field(default="physical_foreign_key")
    confidence: float = Field(default=1.0, le=1.0, ge=0.0)


class TableInfo(BaseModel):
    table_name: str
    schema_name: str | None = None
    table_type: str = "table"
    columns: list[ColumnInfo] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = Field(default_factory=list)
    primary_key_columns: list[str] = Field(default_factory=list)
    comment: str | None = None


class DatabaseInfo(BaseModel):
    database_id: str
    engine_type: str
    database_name: str
    schema_name: str | None = None
    tables: list[TableInfo] = Field(default_factory=list)


class ColumnProfile(BaseModel):
    database_id: str
    table_name: str
    column_name: str
    cardinality: int
    distinct_values: list[str] = Field(default_factory=list)
    sample_values: list[str] = Field(default_factory=list)
