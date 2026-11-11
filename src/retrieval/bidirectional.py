"""Bidirectional hybrid retrieval combining Table-first and Column-first paths."""

from __future__ import annotations

import logging

from src.indexing.hybrid_store import HybridStore
from src.models.documents import ColumnDocument, TableDocument
from src.retrieval.query_parser import QueryParser
from src.retrieval.reranker import CrossEncoderReranker
from src.retrieval.rrf import reciprocal_rank_fusion

logger = logging.getLogger(__name__)


class BidirectionalRetriever:
    """Executes Table-First and Column-First hybrid searches and merges candidates via RRF and reranking."""

    def __init__(
        self,
        hybrid_store: HybridStore,
        reranker: CrossEncoderReranker | None = None,
        query_parser: QueryParser | None = None,
    ):
        self.hybrid_store = hybrid_store
        self.reranker = reranker or CrossEncoderReranker()
        self.query_parser = query_parser or QueryParser()

    def retrieve(
        self,
        query: str,
        database_id: str | None = None,
        table_top_k: int = 15,
        column_top_k: int = 30,
        final_table_limit: int = 6,
    ) -> tuple[list[tuple[TableDocument, float]], list[tuple[ColumnDocument, float]]]:
        parsed = self.query_parser.parse(query)
        enhanced_query = parsed.search_expansion_text if parsed.search_expansion_text else query

        # 1. Table-First Retrieval
        table_first_results = self.hybrid_store.search_tables(
            query=enhanced_query,
            database_id=database_id,
            top_k=table_top_k,
        )

        # 2. Column-First Retrieval
        col_results = self.hybrid_store.search_columns(
            query=enhanced_query,
            database_id=database_id,
            top_k=column_top_k,
        )

        # Map Column results back to parent tables to form Table Candidate List #2
        table_from_cols_dict: dict[str, float] = {}
        for col_doc, score in col_results:
            t_name = col_doc.table_name
            if t_name not in table_from_cols_dict:
                table_from_cols_dict[t_name] = 0.0
            table_from_cols_dict[t_name] = max(table_from_cols_dict[t_name], score)

        # Retrieve table documents corresponding to promoted columns
        table_from_cols_results: list[tuple[TableDocument, float]] = []
        for t_name, score in table_from_cols_dict.items():
            matching_tables = self.hybrid_store.search_tables(
                query=t_name,
                database_id=database_id,
                top_k=1,
            )
            if matching_tables:
                table_from_cols_results.append((matching_tables[0][0], score))

        # 3. Candidate Merging via RRF
        merged_tables = reciprocal_rank_fusion(
            ranked_lists=[table_first_results, table_from_cols_results],
            key_func=lambda td: td.table_name,
            k=60,
        )

        # 4. Cross-Encoder Reranking for Tables
        candidates_to_rerank = [
            {"table_doc": td, "score": sc, "text": td.to_search_text(), "name": td.table_name}
            for td, sc in merged_tables[:table_top_k]
        ]
        reranked_tables_data = self.reranker.rerank(
            query=query,
            candidates=candidates_to_rerank,
            text_key="text",
            top_k=final_table_limit,
        )

        final_tables: list[tuple[TableDocument, float]] = [
            (c["table_doc"], c["rerank_score"]) for c in reranked_tables_data
        ]
        final_table_names = {t.table_name for t, _ in final_tables}

        # Filter relevant columns belonging to the final candidate tables
        relevant_columns: list[tuple[ColumnDocument, float]] = [
            (col, sc) for col, sc in col_results if col.table_name in final_table_names
        ]

        return final_tables, relevant_columns
