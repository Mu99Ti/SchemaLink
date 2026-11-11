"""Unified Qdrant hybrid vector & lexical store."""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

from src.indexing.embeddings import EmbeddingService
from src.models.documents import ColumnDocument, DatabaseDocument, ExemplarDocument, TableDocument

logger = logging.getLogger(__name__)


class HybridStore:
    """Manages Qdrant vector collections and payload lexical/metadata filtering."""

    def __init__(
        self,
        qdrant_client: QdrantClient | None = None,
        embedding_service: EmbeddingService | None = None,
        path: str | None = None,
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        if qdrant_client:
            self.client = qdrant_client
        elif path:
            self.client = QdrantClient(path=path)
        else:
            self.client = QdrantClient(location=":memory:")

        self.db_collection = "schemalink_databases"
        self.table_collection = "schemalink_tables"
        self.column_collection = "schemalink_columns"
        self.exemplar_collection = "schemalink_exemplars"

        self._ensure_collections()

    def _ensure_collections(self) -> None:
        collections = [
            self.db_collection,
            self.table_collection,
            self.column_collection,
            self.exemplar_collection,
        ]
        dim = 384
        for name in collections:
            try:
                self.client.get_collection(name)
            except Exception:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
                )

    # 1. Databases Indexing & Search
    def index_database(self, doc: DatabaseDocument) -> None:
        vector = self.embedding_service.embed_query(doc.to_search_text())
        point_id = abs(hash(doc.document_id)) % (10**15)
        self.client.upsert(
            collection_name=self.db_collection,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=doc.model_dump(),
                )
            ],
        )

    def _query(
        self, collection_name: str, query_vector: list[float], query_filter: Any = None, limit: int = 10
    ) -> list[Any]:
        """Internal helper for querying points across qdrant-client versions."""
        if hasattr(self.client, "query_points"):
            res = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
            )
            return res.points
        else:
            return self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
            )

    def search_databases(self, query: str, top_k: int = 3) -> list[tuple[DatabaseDocument, float]]:
        vector = self.embedding_service.embed_query(query)
        points = self._query(
            collection_name=self.db_collection,
            query_vector=vector,
            limit=top_k,
        )
        return [(DatabaseDocument(**p.payload), p.score) for p in points]

    # 2. Tables Indexing & Search
    def index_tables(self, docs: list[TableDocument]) -> None:
        if not docs:
            return
        texts = [d.to_search_text() for d in docs]
        vectors = self.embedding_service.embed_texts(texts)

        points = []
        for doc, vec in zip(docs, vectors, strict=False):
            point_id = abs(hash(doc.document_id)) % (10**15)
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vec,
                    payload=doc.model_dump(),
                )
            )
        self.client.upsert(collection_name=self.table_collection, points=points)

    def search_tables(
        self, query: str, database_id: str | None = None, top_k: int = 15
    ) -> list[tuple[TableDocument, float]]:
        vector = self.embedding_service.embed_query(query)
        q_filter = None
        if database_id:
            q_filter = models.Filter(
                must=[models.FieldCondition(key="database_id", match=models.MatchValue(value=database_id))]
            )

        points = self._query(
            collection_name=self.table_collection,
            query_vector=vector,
            query_filter=q_filter,
            limit=top_k,
        )
        return [(TableDocument(**p.payload), p.score) for p in points]

    # 3. Columns Indexing & Search
    def index_columns(self, docs: list[ColumnDocument]) -> None:
        if not docs:
            return
        texts = [d.to_search_text() for d in docs]
        vectors = self.embedding_service.embed_texts(texts)

        points = []
        for doc, vec in zip(docs, vectors, strict=False):
            point_id = abs(hash(doc.document_id)) % (10**15)
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vec,
                    payload=doc.model_dump(),
                )
            )
        self.client.upsert(collection_name=self.column_collection, points=points)

    def search_columns(
        self, query: str, database_id: str | None = None, top_k: int = 30
    ) -> list[tuple[ColumnDocument, float]]:
        vector = self.embedding_service.embed_query(query)
        q_filter = None
        if database_id:
            q_filter = models.Filter(
                must=[models.FieldCondition(key="database_id", match=models.MatchValue(value=database_id))]
            )

        points = self._query(
            collection_name=self.column_collection,
            query_vector=vector,
            query_filter=q_filter,
            limit=top_k,
        )
        return [(ColumnDocument(**p.payload), p.score) for p in points]

    # 4. Exemplar Memory Store
    def index_exemplar(self, exemplar: ExemplarDocument) -> None:
        vector = self.embedding_service.embed_query(exemplar.to_search_text())
        point_id = abs(hash(exemplar.document_id)) % (10**15)
        self.client.upsert(
            collection_name=self.exemplar_collection,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=exemplar.model_dump(),
                )
            ],
        )

    def search_exemplars(
        self, query: str, database_id: str | None = None, top_k: int = 3
    ) -> list[tuple[ExemplarDocument, float]]:
        vector = self.embedding_service.embed_query(query)
        q_filter = None
        if database_id:
            q_filter = models.Filter(
                must=[models.FieldCondition(key="database_id", match=models.MatchValue(value=database_id))]
            )

        points = self._query(
            collection_name=self.exemplar_collection,
            query_vector=vector,
            query_filter=q_filter,
            limit=top_k,
        )
        return [(ExemplarDocument(**p.payload), p.score) for p in points]
