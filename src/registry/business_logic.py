"""Business logic and semantic annotation registry."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class VirtualForeignKey(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str = "virtual_foreign_key"
    confidence: float = 0.95
    description: str | None = None


class TableAnnotation(BaseModel):
    table_name: str
    business_synonyms: list[str] = Field(default_factory=list)
    description: str | None = None
    business_rules: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ColumnAnnotation(BaseModel):
    table_name: str
    column_name: str
    business_synonyms: list[str] = Field(default_factory=list)
    description: str | None = None
    calculation_formula: str | None = None
    tags: list[str] = Field(default_factory=list)


class DatabaseAnnotation(BaseModel):
    database_id: str
    domains: list[str] = Field(default_factory=list)
    description: str | None = None
    tables: dict[str, TableAnnotation] = Field(default_factory=dict)
    columns: dict[str, ColumnAnnotation] = Field(default_factory=dict)
    virtual_foreign_keys: list[VirtualForeignKey] = Field(default_factory=list)


class BusinessLogicRegistry:
    """Manages custom domain annotations, synonyms, and virtual joins."""

    def __init__(self, storage_dir: str | None = None):
        self.storage_dir = Path(storage_dir) if storage_dir else None
        if self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._db_annotations: dict[str, DatabaseAnnotation] = {}

    def get_database_annotation(self, database_id: str) -> DatabaseAnnotation:
        if database_id not in self._db_annotations:
            self._load_from_disk(database_id)
        if database_id not in self._db_annotations:
            self._db_annotations[database_id] = DatabaseAnnotation(database_id=database_id)
        return self._db_annotations[database_id]

    def set_database_annotation(self, annotation: DatabaseAnnotation) -> None:
        self._db_annotations[annotation.database_id] = annotation
        self._save_to_disk(annotation.database_id)

    def add_table_annotation(self, database_id: str, table_annotation: TableAnnotation) -> None:
        db_ann = self.get_database_annotation(database_id)
        db_ann.tables[table_annotation.table_name] = table_annotation
        self._save_to_disk(database_id)

    def add_column_annotation(self, database_id: str, col_annotation: ColumnAnnotation) -> None:
        db_ann = self.get_database_annotation(database_id)
        key = f"{col_annotation.table_name}.{col_annotation.column_name}"
        db_ann.columns[key] = col_annotation
        self._save_to_disk(database_id)

    def add_virtual_foreign_key(self, database_id: str, vfk: VirtualForeignKey) -> None:
        db_ann = self.get_database_annotation(database_id)
        # Avoid duplicate edges
        existing = [
            f
            for f in db_ann.virtual_foreign_keys
            if f.source_table == vfk.source_table
            and f.source_column == vfk.source_column
            and f.target_table == vfk.target_table
            and f.target_column == vfk.target_column
        ]
        if not existing:
            db_ann.virtual_foreign_keys.append(vfk)
            self._save_to_disk(database_id)

    def _save_to_disk(self, database_id: str) -> None:
        if not self.storage_dir:
            return
        file_path = self.storage_dir / f"{database_id}_annotations.json"
        data = self._db_annotations[database_id].model_dump()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_from_disk(self, database_id: str) -> None:
        if not self.storage_dir:
            return
        file_path = self.storage_dir / f"{database_id}_annotations.json"
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                    self._db_annotations[database_id] = DatabaseAnnotation(**data)
            except Exception:
                pass
