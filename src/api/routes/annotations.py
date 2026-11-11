"""Business logic and annotations API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.registry.business_logic import (
    ColumnAnnotation,
    DatabaseAnnotation,
    TableAnnotation,
    VirtualForeignKey,
)

router = APIRouter(prefix="/api/v1/databases/{database_id}/annotations", tags=["Annotations"])


@router.get("")
def get_annotations(database_id: str, request: Request):
    engine = request.app.state.schemalink
    ann = engine.registry.get_database_annotation(database_id)
    return ann.model_dump()


@router.post("")
def update_annotations(database_id: str, annotation: DatabaseAnnotation, request: Request):
    engine = request.app.state.schemalink
    annotation.database_id = database_id
    engine.registry.set_database_annotation(annotation)
    return {"database_id": database_id, "status": "updated"}


@router.post("/tables")
def add_table_annotation(database_id: str, table_ann: TableAnnotation, request: Request):
    engine = request.app.state.schemalink
    engine.registry.add_table_annotation(database_id, table_ann)
    return {"database_id": database_id, "table": table_ann.table_name, "status": "added"}


@router.post("/columns")
def add_column_annotation(database_id: str, col_ann: ColumnAnnotation, request: Request):
    engine = request.app.state.schemalink
    engine.registry.add_column_annotation(database_id, col_ann)
    return {"database_id": database_id, "column": f"{col_ann.table_name}.{col_ann.column_name}", "status": "added"}


@router.post("/virtual-joins")
def add_virtual_join(database_id: str, vfk: VirtualForeignKey, request: Request):
    engine = request.app.state.schemalink
    engine.registry.add_virtual_foreign_key(database_id, vfk)
    return {"database_id": database_id, "virtual_join": f"{vfk.source_table}->{vfk.target_table}", "status": "added"}
