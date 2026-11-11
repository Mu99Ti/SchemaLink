"""Unit tests for SchemaLink engine, Autonomous mode, and HITL workflow."""

import pytest

from src.engine import SchemaLink
from tests.fixtures.sample_db import create_ecommerce_test_db


@pytest.fixture
def test_db_path(tmp_path):
    db_file = tmp_path / "test_ecommerce.db"
    create_ecommerce_test_db(str(db_file))
    return str(db_file)


def test_schemalink_autonomous_pipeline(test_db_path, tmp_path):
    engine = SchemaLink(storage_dir=str(tmp_path))
    engine.register_database("sales_db", f"sqlite:///{test_db_path}")

    index_res = engine.index_database("sales_db")
    assert index_res["status"] == "indexed"
    assert index_res["tables_indexed"] == 5

    # Run Autonomous Retrieval
    context = engine.retrieve_sync(
        query="Total revenue by branch in California",
        database_id="sales_db",
        mode="autonomous",
    )

    assert context.database_id == "sales_db"
    table_names = {t.table_name for t in context.selected_tables}
    assert "branches" in table_names or "orders" in table_names
    assert context.provenance.mode == "autonomous"
    assert len(context.formatted_ddl) > 0


def test_schemalink_hitl_pipeline(test_db_path, tmp_path):
    engine = SchemaLink(storage_dir=str(tmp_path))
    engine.register_database("sales_db", f"sqlite:///{test_db_path}")
    engine.index_database("sales_db")

    # Step 1: Initiate HITL
    hitl_state = engine.initiate_hitl(
        query="Show customer purchases",
        database_id="sales_db",
    )

    assert hitl_state.status == "awaiting_feedback"
    assert len(hitl_state.candidate_tables) > 0

    # Step 2: Human reviews & approves tables
    approved_tables = ["customers", "orders"]
    final_context = engine.submit_hitl_feedback(
        state=hitl_state,
        approved_tables=approved_tables,
    )

    assert final_context.provenance.mode == "hitl"
    selected_table_names = {t.table_name for t in final_context.selected_tables}
    assert selected_table_names == {"customers", "orders"}

    # Step 3: Verify Exemplar Memory was indexed
    exemplars = engine.hybrid_store.search_exemplars("customer purchases", database_id="sales_db")
    assert len(exemplars) > 0
    assert exemplars[0][0].approved_tables == approved_tables
