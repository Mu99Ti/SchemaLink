"""Database management API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/databases", tags=["Databases"])


class RegisterDatabaseRequest(BaseModel):
    database_id: str
    connection_uri: str
    options: dict[str, Any] | None = None


class IndexDatabaseRequest(BaseModel):
    schema_name: str | None = None
    profile_enums: bool = True


@router.post("")
def register_database(req: RegisterDatabaseRequest, request: Request):
    engine = request.app.state.schemalink
    try:
        engine.register_database(
            database_id=req.database_id,
            connection_uri=req.connection_uri,
            options=req.options,
        )
        return {"database_id": req.database_id, "status": "registered"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{database_id}/index")
def index_database(database_id: str, req: IndexDatabaseRequest, request: Request):
    engine = request.app.state.schemalink
    try:
        result = engine.index_database(
            database_id=database_id,
            schema_name=req.schema_name,
            profile_enums=req.profile_enums,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
