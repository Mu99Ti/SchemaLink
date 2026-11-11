"""Top-level SchemaLink Facade uniting catalog, indexing, retrieval, and workflow."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.catalog.profiler import CategoricalProfiler
from src.connectors.base import BaseConnector
from src.connectors.factory import create_connector
from src.context.compactor import SchemaContextCompactor
from src.graph.schema_graph import SchemaRelationshipGraph
from src.indexing.document_builder import SchemaDocumentBuilder
from src.indexing.embeddings import EmbeddingService
from src.indexing.hybrid_store import HybridStore
from src.models.context import CuratedSchemaContext
from src.registry.business_logic import BusinessLogicRegistry
from src.retrieval.bidirectional import BidirectionalRetriever
from src.retrieval.query_parser import QueryParser
from src.retrieval.reranker import CrossEncoderReranker
from src.workflow.graph import SchemaLinkWorkflow, WorkflowState

logger = logging.getLogger(__name__)


class SchemaLink:
    """High-precision Schema RAG and Discovery Engine."""

    def __init__(
        self,
        storage_dir: str | None = "./schemalink_data",
        qdrant_path: str | None = None,
        embedding_model: str = "BAAI/bge-small-en-v1.5",
        enable_reranker: bool = True,
    ):
        self.storage_dir = Path(storage_dir) if storage_dir else None
        if self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.registry = BusinessLogicRegistry(
            storage_dir=str(self.storage_dir / "annotations") if self.storage_dir else None
        )
        self.embedding_service = EmbeddingService(model_name=embedding_model)
        self.hybrid_store = HybridStore(
            embedding_service=self.embedding_service,
            path=qdrant_path or (str(self.storage_dir / "qdrant") if self.storage_dir else None),
        )
        self.document_builder = SchemaDocumentBuilder(registry=self.registry)
        self.reranker = CrossEncoderReranker() if enable_reranker else None
        self.query_parser = QueryParser()
        self.retriever = BidirectionalRetriever(
            hybrid_store=self.hybrid_store,
            reranker=self.reranker,
            query_parser=self.query_parser,
        )
        self.compactor = SchemaContextCompactor()

        self.connectors: dict[str, BaseConnector] = {}
        self.graphs: dict[str, SchemaRelationshipGraph] = {}
        self.workflow = SchemaLinkWorkflow(
            hybrid_store=self.hybrid_store,
            graphs=self.graphs,
            retriever=self.retriever,
            compactor=self.compactor,
        )

    def register_database(
        self,
        database_id: str,
        connection_uri: str,
        options: dict[str, Any] | None = None,
    ) -> BaseConnector:
        """Registers a database connector."""
        connector = create_connector(database_id, connection_uri, options=options)
        self.connectors[database_id] = connector
        return connector

    def index_database(
        self,
        database_id: str,
        schema_name: str | None = None,
        profile_enums: bool = True,
    ) -> dict[str, Any]:
        """Introspects database, profiles categorical values, builds documents, and indexes into Qdrant."""
        connector = self.connectors.get(database_id)
        if not connector:
            raise ValueError(f"Database {database_id} is not registered. Call register_database first.")

        db_info = connector.introspect(schema_name=schema_name)

        # Profile categorical columns
        profiles = {}
        if profile_enums:
            profiler = CategoricalProfiler(connector)
            profiles = profiler.profile_database(db_info)

        # Build in-memory relationship graph
        graph = SchemaRelationshipGraph(database_id=database_id)
        graph.build_from_catalog(db_info, registry=self.registry)
        self.graphs[database_id] = graph

        # Build multi-granularity documents
        db_doc, table_docs, column_docs = self.document_builder.build_documents(db_info, profiles=profiles)

        # Index documents in hybrid store
        self.hybrid_store.index_database(db_doc)
        self.hybrid_store.index_tables(table_docs)
        self.hybrid_store.index_columns(column_docs)

        return {
            "database_id": database_id,
            "status": "indexed",
            "tables_indexed": len(table_docs),
            "columns_indexed": len(column_docs),
            "categorical_profiles": len(profiles),
        }

    async def retrieve(
        self,
        query: str,
        database_id: str | None = None,
        mode: str = "autonomous",
    ) -> CuratedSchemaContext:
        """Retrieves minimal, high-precision schema context for a natural language query."""
        state = self.workflow.run(query=query, database_id=database_id, mode=mode)
        if state.final_context is None:
            raise RuntimeError(f"Workflow did not complete (status: {state.status}). If using HITL, review candidates first.")
        return state.final_context

    def retrieve_sync(
        self,
        query: str,
        database_id: str | None = None,
        mode: str = "autonomous",
    ) -> CuratedSchemaContext:
        """Synchronous version of retrieve."""
        state = self.workflow.run(query=query, database_id=database_id, mode=mode)
        if state.final_context is None:
            raise RuntimeError(f"Workflow did not complete (status: {state.status})")
        return state.final_context

    def initiate_hitl(self, query: str, database_id: str | None = None) -> WorkflowState:
        """Initiates a HITL workflow session and pauses for human inspection."""
        return self.workflow.run(query=query, database_id=database_id, mode="hitl")

    def submit_hitl_feedback(
        self,
        state: WorkflowState,
        approved_tables: list[str],
        approved_columns: list[dict[str, str]] | None = None,
        approved_joins: list[dict[str, str]] | None = None,
    ) -> CuratedSchemaContext:
        """Resumes a paused HITL workflow with approved selections."""
        resumed_state = self.workflow.resume_hitl(
            state=state,
            approved_tables=approved_tables,
            approved_columns=approved_columns,
            approved_joins=approved_joins,
        )
        if resumed_state.final_context is None:
            raise RuntimeError("Context assembly failed after feedback")
        return resumed_state.final_context
