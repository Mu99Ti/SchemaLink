"""Schema retrieval and Human-in-the-Loop API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.workflow.graph import WorkflowState

router = APIRouter(prefix="/api/v1/retrieval", tags=["Retrieval"])

# In-memory session store for HITL state
HITL_SESSIONS: dict[str, WorkflowState] = {}


class SchemaRetrievalRequest(BaseModel):
    query: str
    database_id: str | None = None
    mode: str = Field(default="autonomous", description="'autonomous' or 'hitl'")


class HitlFeedbackRequest(BaseModel):
    session_id: str
    approved_tables: list[str]
    approved_columns: list[dict[str, str]] | None = None
    approved_joins: list[dict[str, str]] | None = None


@router.post("/schema")
def retrieve_schema(req: SchemaRetrievalRequest, request: Request):
    engine = request.app.state.schemalink
    try:
        if req.mode == "autonomous":
            context = engine.retrieve_sync(
                query=req.query,
                database_id=req.database_id,
                mode="autonomous",
            )
            return context.model_dump()
        else:
            # Initiate HITL session
            session_id = f"hitl_{uuid.uuid4().hex[:8]}"
            state = engine.initiate_hitl(query=req.query, database_id=req.database_id)
            HITL_SESSIONS[session_id] = state

            candidate_tables = [
                {
                    "table": t[0].table_name,
                    "description": t[0].description,
                    "confidence": round(t[1], 4),
                    "selected": True,
                }
                for t in state.candidate_tables
            ]
            candidate_columns = [
                {
                    "table": c[0].table_name,
                    "column": c[0].column_name,
                    "data_type": c[0].data_type,
                    "description": c[0].description,
                    "selected": True,
                }
                for c in state.candidate_columns
            ]
            suggested_joins = [jp.model_dump() for jp in state.resolved_join_paths]

            return {
                "session_id": session_id,
                "status": "awaiting_feedback",
                "database_id": state.database_id,
                "query": req.query,
                "candidate_tables": candidate_tables,
                "candidate_columns": candidate_columns,
                "suggested_joins": suggested_joins,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/feedback")
def submit_hitl_feedback(req: HitlFeedbackRequest, request: Request):
    engine = request.app.state.schemalink
    state = HITL_SESSIONS.get(req.session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found or expired")

    try:
        context = engine.submit_hitl_feedback(
            state=state,
            approved_tables=req.approved_tables,
            approved_columns=req.approved_columns,
            approved_joins=req.approved_joins,
        )
        # Clean up session
        del HITL_SESSIONS[req.session_id]
        return context.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
