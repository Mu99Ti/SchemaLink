"""Real-world integration test of SchemaLink against the Northwind database (600k+ rows)."""

import os

import pytest

from src.engine import SchemaLink

NORTHWIND_DB_PATH = "/Users/muhamadtalebi/Developer/prompt2sql-local/data/databases/northwind.db"


@pytest.mark.skipif(not os.path.exists(NORTHWIND_DB_PATH), reason="Northwind database not found")
def test_northwind_indexing_and_retrieval(tmp_path):
    engine = SchemaLink(storage_dir=str(tmp_path / "northwind_engine"))
    connection_uri = f"sqlite:///{NORTHWIND_DB_PATH}"

    # 1. Register Database
    engine.register_database("northwind_db", connection_uri)

    # 2. Introspect & Index Schema
    index_res = engine.index_database("northwind_db", profile_enums=True)
    assert index_res["status"] == "indexed"
    assert index_res["tables_indexed"] >= 10
    print(f"\n[Northwind] Tables Indexed: {index_res['tables_indexed']}")
    print(f"[Northwind] Columns Indexed: {index_res['columns_indexed']}")
    print(f"[Northwind] Categorical Enums Profiled: {index_res['categorical_profiles']}")

    # 3. Test Question 1: Sales revenue by product category
    q1 = "Total sales revenue by product category"
    ctx1 = engine.retrieve_sync(q1, database_id="northwind_db")
    selected_t1 = {t.table_name.lower() for t in ctx1.selected_tables}
    print(f"\n[Q1: '{q1}'] Selected Tables: {selected_t1}")
    print("[Q1 Compact DDL Output]:\n" + ctx1.to_prompt("compact_ddl"))

    assert any("category" in t for t in selected_t1) or "products" in selected_t1

    # 4. Test Question 2: Multi-hop query with filter
    q2 = "Which employees handled orders for customers in Germany"
    ctx2 = engine.retrieve_sync(q2, database_id="northwind_db")
    selected_t2 = {t.table_name.lower() for t in ctx2.selected_tables}
    print(f"\n[Q2: '{q2}'] Selected Tables: {selected_t2}")

    assert "orders" in selected_t2 or "employees" in selected_t2 or "customers" in selected_t2

    # 5. Test Question 3: Bridge Table Discovery (Customers to Categories)
    graph = engine.graphs["northwind_db"]
    connected_tables, joins = graph.find_connecting_subgraph(["Customers", "Categories"])
    connected_lower = [t.lower() for t in connected_tables]
    print(f"\n[Bridge Discovery Customers -> Categories]: {connected_lower}")
    print(f"[Discovered Join Paths]: {[f'{j.source_table}.{j.source_column} = {j.target_table}.{j.target_column}' for j in joins]}")

    assert "orders" in connected_lower or "order details" in connected_lower
    assert len(joins) >= 2


@pytest.mark.skipif(not os.path.exists(NORTHWIND_DB_PATH), reason="Northwind database not found")
def test_northwind_hitl_workflow(tmp_path):
    engine = SchemaLink(storage_dir=str(tmp_path / "northwind_hitl"))
    engine.register_database("northwind_db", f"sqlite:///{NORTHWIND_DB_PATH}")
    engine.index_database("northwind_db", profile_enums=False)

    # Initiate HITL
    query = "List suppliers and products shipped by Speedy Express"
    state = engine.initiate_hitl(query, database_id="northwind_db")

    assert state.status == "awaiting_feedback"
    assert len(state.candidate_tables) > 0
    candidate_names = [t[0].table_name for t in state.candidate_tables]
    print(f"\n[HITL Inspection Candidate Tables]: {candidate_names}")

    # Human approves Products and Suppliers
    approved = ["Products", "Suppliers"]
    ctx = engine.submit_hitl_feedback(state, approved_tables=approved)

    assert ctx.provenance.mode == "hitl"
    assert {t.table_name for t in ctx.selected_tables} == {"Products", "Suppliers"}

    # Verify Exemplar was saved
    exemplars = engine.hybrid_store.search_exemplars(query, database_id="northwind_db")
    assert len(exemplars) > 0
    assert exemplars[0][0].approved_tables == approved
