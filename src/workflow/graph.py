"""LangGraph workflow definition for Autonomous and Human-in-the-Loop execution."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from src.context.compactor import SchemaContextCompactor
from src.graph.schema_graph import SchemaRelationshipGraph
from src.indexing.hybrid_store import HybridStore
from src.models.context import CuratedSchemaContext, JoinPath
from src.models.documents import ColumnDocument, TableDocument
from src.retrieval.bidirectional import BidirectionalRetriever

logger = logging.getLogger(__name__)


class WorkflowState(BaseModel):
    query: str
    database_id: str | None = None
    engine_type: str = "sqlite"
    mode: str = "autonomous"  # 'autonomous' or 'hitl'
    status: str = "init"  # 'init', 'awaiting_feedback', 'completed'

    # Candidate proposals
    candidate_tables: list[tuple[TableDocument, float]] = Field(default_factory=list)
    candidate_columns: list[tuple[ColumnDocument, float]] = Field(default_factory=list)
    resolved_join_paths: list[JoinPath] = Field(default_factory=list)

    # Human feedback inputs (for HITL mode)
    user_approved_tables: list[str] | None = None
    user_approved_columns: list[dict[str, str]] | None = None
    user_approved_joins: list[dict[str, str]] | None = None

    # Output context
    final_context: CuratedSchemaContext | None = None


class SchemaLinkWorkflow:
    """Orchestrates multi-DB routing, bidirectional retrieval, graph resolution, and HITL state."""

    def __init__(
        self,
        hybrid_store: HybridStore,
        graphs: dict[str, SchemaRelationshipGraph],
        retriever: BidirectionalRetriever | None = None,
        compactor: SchemaContextCompactor | None = None,
    ):
        self.hybrid_store = hybrid_store
        self.graphs = graphs
        self.retriever = retriever or BidirectionalRetriever(hybrid_store=hybrid_store)
        self.compactor = compactor or SchemaContextCompactor()

    def route_database(self, state: WorkflowState) -> WorkflowState:
        if state.database_id:
            return state

        db_candidates = self.hybrid_store.search_databases(state.query, top_k=1)
        if db_candidates:
            state.database_id = db_candidates[0][0].database_id
            state.engine_type = db_candidates[0][0].engine_type
        else:
            state.database_id = "default_db"
        return state

    def retrieve_candidates(self, state: WorkflowState) -> WorkflowState:
        tables, columns = self.retriever.retrieve(
            query=state.query,
            database_id=state.database_id,
        )
        state.candidate_tables = tables
        state.candidate_columns = columns

        # Resolve join paths
        target_table_names = [t.table_name for t, _ in tables]
        graph = self.graphs.get(state.database_id or "")
        if graph:
            connected_tables, joins = graph.find_connecting_subgraph(target_table_names)
            state.resolved_join_paths = joins

            # If intermediate bridge tables were found, fetch their table documents
            existing_names = {t.table_name for t, _ in state.candidate_tables}
            for t_name in connected_tables:
                if t_name not in existing_names:
                    res = self.hybrid_store.search_tables(t_name, database_id=state.database_id, top_k=1)
                    if res:
                        state.candidate_tables.append((res[0][0], 0.75))
        return state

    def hitl_pause_or_continue(self, state: WorkflowState) -> WorkflowState:
        if state.mode == "hitl" and state.user_approved_tables is None:
            # Mark state as awaiting feedback so API/Caller can return inspection payload
            state.status = "awaiting_feedback"
            return state

        state.status = "processing_feedback"
        return state

    def assemble_final_context(self, state: WorkflowState) -> WorkflowState:
        # Apply user feedback if provided
        final_tables = list(state.candidate_tables)
        if state.user_approved_tables is not None:
            approved_set = set(state.user_approved_tables)
            final_tables = [t for t in state.candidate_tables if t[0].table_name in approved_set]
            existing_names = {t[0].table_name for t in final_tables}

            # If user added a table not previously in candidates, fetch it
            for t_name in approved_set:
                if t_name not in existing_names:
                    res = self.hybrid_store.search_tables(t_name, database_id=state.database_id, top_k=1)
                    if res:
                        final_tables.append((res[0][0], 1.0))
                    existing_names.add(t_name)

        final_columns = state.candidate_columns
        if state.user_approved_columns is not None:
            approved_cols = {(c["table"], c["column"]) for c in state.user_approved_columns}
            final_columns = [
                c for c in state.candidate_columns if (c[0].table_name, c[0].column_name) in approved_cols
            ]

        final_joins = state.resolved_join_paths

        context = self.compactor.build_context(
            database_id=state.database_id or "default_db",
            engine_type=state.engine_type,
            query=state.query,
            tables=final_tables,
            columns=final_columns,
            join_paths=final_joins,
            mode=state.mode,
        )
        state.final_context = context
        state.status = "completed"
        return state

    def run(self, query: str, database_id: str | None = None, mode: str = "autonomous") -> WorkflowState:
        """Executes the complete workflow."""
        state = WorkflowState(query=query, database_id=database_id, mode=mode)
        state = self.route_database(state)
        state = self.retrieve_candidates(state)
        state = self.hitl_pause_or_continue(state)

        if state.status != "awaiting_feedback":
            state = self.assemble_final_context(state)
        return state

    def resume_hitl(
        self,
        state: WorkflowState,
        approved_tables: list[str],
        approved_columns: list[dict[str, str]] | None = None,
        approved_joins: list[dict[str, str]] | None = None,
    ) -> WorkflowState:
        """Resumes a paused HITL workflow with human feedback."""
        state.user_approved_tables = approved_tables
        state.user_approved_columns = approved_columns
        state.user_approved_joins = approved_joins
        state = self.assemble_final_context(state)

        # Index approved exemplar to learn for future queries
        import uuid
        from datetime import datetime

        from src.models.documents import ExemplarDocument
        from src.utils.hashing import content_hash

        exemplar = ExemplarDocument(
            document_id=f"ex_{uuid.uuid4().hex[:8]}",
            database_id=state.database_id or "default_db",
            query=state.query,
            approved_tables=approved_tables,
            approved_columns=approved_columns or [],
            approved_joins=approved_joins or [],
            timestamp=datetime.utcnow().isoformat(),
            content_hash=content_hash(state.query, "".join(approved_tables)),
        )
        self.hybrid_store.index_exemplar(exemplar)

        return state
