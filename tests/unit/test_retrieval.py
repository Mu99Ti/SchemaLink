"""Unit tests for query parsing, document builder, graph join resolver, and compactor."""

import pytest

from src.connectors.base import SQLAlchemyConnector
from src.context.compactor import SchemaContextCompactor
from src.graph.schema_graph import SchemaRelationshipGraph
from src.indexing.document_builder import SchemaDocumentBuilder
from src.indexing.hybrid_store import HybridStore
from src.retrieval.bidirectional import BidirectionalRetriever
from src.retrieval.query_parser import QueryParser
from tests.fixtures.sample_db import create_ecommerce_test_db


@pytest.fixture
def test_db_path(tmp_path):
    db_file = tmp_path / "test_ecommerce.db"
    create_ecommerce_test_db(str(db_file))
    return str(db_file)


def test_query_parser():
    parser = QueryParser()
    parsed = parser.parse("Show monthly revenue by branch in California after 2024")
    assert parsed.result_grain == "branch"
    assert "California" in [f.value for f in parsed.filters]
    assert any(f.operator == ">" and f.value == "2024" for f in parsed.filters)
    assert "Show monthly revenue by branch" in parsed.search_expansion_text

    # Test negation / antijoin detection
    neg_parsed = parser.parse("Find customers without any orders")
    assert neg_parsed.is_negation is True
    assert neg_parsed.intent_type == "negation"


def test_schema_relationship_graph(test_db_path):
    uri = f"sqlite:///{test_db_path}"
    connector = SQLAlchemyConnector("sales_db", uri)
    db_info = connector.introspect()

    graph = SchemaRelationshipGraph("sales_db")
    graph.build_from_catalog(db_info)

    # Test connecting subgraph between customers and products
    # Path should be: customers -> orders -> order_items -> products
    connected_tables, joins = graph.find_connecting_subgraph(["customers", "products"])
    assert "orders" in connected_tables
    assert "order_items" in connected_tables
    assert len(joins) >= 3


def test_document_builder_and_hybrid_store(test_db_path):
    uri = f"sqlite:///{test_db_path}"
    connector = SQLAlchemyConnector("sales_db", uri)
    db_info = connector.introspect()

    builder = SchemaDocumentBuilder()
    db_doc, table_docs, column_docs = builder.build_documents(db_info)

    assert len(table_docs) == 5
    assert len(column_docs) > 15

    store = HybridStore()
    store.index_database(db_doc)
    store.index_tables(table_docs)
    store.index_columns(column_docs)

    # Search tables
    found_tables = store.search_tables("customer purchases and orders", top_k=2)
    assert len(found_tables) > 0
    table_names = [t[0].table_name for t in found_tables]
    assert "orders" in table_names


def test_bidirectional_retrieval_and_compaction(test_db_path):
    uri = f"sqlite:///{test_db_path}"
    connector = SQLAlchemyConnector("sales_db", uri)
    db_info = connector.introspect()

    builder = SchemaDocumentBuilder()
    db_doc, table_docs, column_docs = builder.build_documents(db_info)

    store = HybridStore()
    store.index_database(db_doc)
    store.index_tables(table_docs)
    store.index_columns(column_docs)

    graph = SchemaRelationshipGraph("sales_db")
    graph.build_from_catalog(db_info)

    retriever = BidirectionalRetriever(hybrid_store=store)
    tables, columns = retriever.retrieve("Show monthly sales by branch", database_id="sales_db")

    assert len(tables) > 0

    compactor = SchemaContextCompactor()
    context = compactor.build_context(
        database_id="sales_db",
        engine_type="sqlite",
        query="Show monthly sales by branch",
        tables=tables,
        columns=columns,
        join_paths=[],
    )

    assert len(context.selected_tables) > 0
    assert context.formatted_ddl is not None
    assert "CREATE TABLE" in context.formatted_ddl
