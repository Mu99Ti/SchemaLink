"""Curated schema context models returned to downstream Query Agents."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SelectedColumn(BaseModel):
    name: str
    data_type: str
    is_primary_key: bool = False
    is_foreign_key: bool = False
    description: str | None = None
    matched_literal: str | None = None


class SelectedTable(BaseModel):
    table_name: str
    schema_name: str | None = None
    description: str | None = None
    columns: list[SelectedColumn] = Field(default_factory=list)
    omitted_columns_count: int = 0
    omitted_column_names: list[str] = Field(default_factory=list)


class JoinPath(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str = "physical_foreign_key"
    confidence: float = 1.0


class ProvenanceInfo(BaseModel):
    mode: str
    retrieval_strategy: str = "bidirectional_hybrid_rrf_rerank"
    confidence_score: float = 1.0
    index_version: str = "v1"
    tables_retrieved: int = 0
    columns_retrieved: int = 0


class CuratedSchemaContext(BaseModel):
    database_id: str
    engine_type: str
    query: str
    selected_tables: list[SelectedTable] = Field(default_factory=list)
    join_paths: list[JoinPath] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    provenance: ProvenanceInfo
    formatted_ddl: str | None = None

    def to_prompt(self, format_type: str = "compact_ddl") -> str:
        if format_type == "compact_ddl" and self.formatted_ddl:
            return self.formatted_ddl
        return self.model_dump_json(indent=2)
