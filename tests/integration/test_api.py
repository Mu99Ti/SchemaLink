"""Integration tests for SchemaLink FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.api.server import create_app
from src.engine import SchemaLink
from tests.fixtures.sample_db import create_ecommerce_test_db


@pytest.fixture
def test_app_and_db(tmp_path):
    db_file = tmp_path / "api_test.db"
    create_ecommerce_test_db(str(db_file))

    engine = SchemaLink(storage_dir=str(tmp_path / "engine_data"))
    app = create_app(engine)
    client = TestClient(app)
    return client, str(db_file)


def test_api_full_lifecycle(test_app_and_db):
    client, db_path = test_app_and_db

    # 1. Health check
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 2. Register Database
    resp = client.post(
        "/api/v1/databases",
        json={"database_id": "test_db", "connection_uri": f"sqlite:///{db_path}"},
    )
    assert resp.status_code == 200

    # 3. Index Database
    resp = client.post("/api/v1/databases/test_db/index", json={"profile_enums": True})
    assert resp.status_code == 200
    assert resp.json()["tables_indexed"] == 5

    # 4. Inject Business Annotation
    resp = client.post(
        "/api/v1/databases/test_db/annotations/tables",
        json={
            "table_name": "orders",
            "business_synonyms": ["purchases", "sales"],
            "business_rules": ["Filter completed orders"],
            "tags": ["finance"],
        },
    )
    assert resp.status_code == 200

    # 5. Autonomous Retrieval
    resp = client.post(
        "/api/v1/retrieval/schema",
        json={"query": "Show monthly sales by branch", "database_id": "test_db", "mode": "autonomous"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "selected_tables" in data
    assert len(data["selected_tables"]) > 0

    # 6. HITL Retrieval & Feedback
    hitl_resp = client.post(
        "/api/v1/retrieval/schema",
        json={"query": "Show orders and items", "database_id": "test_db", "mode": "hitl"},
    )
    assert hitl_resp.status_code == 200
    hitl_data = hitl_resp.json()
    assert hitl_data["status"] == "awaiting_feedback"
    session_id = hitl_data["session_id"]

    # Submit feedback
    feedback_resp = client.post(
        "/api/v1/retrieval/feedback",
        json={
            "session_id": session_id,
            "approved_tables": ["orders", "order_items"],
        },
    )
    assert feedback_resp.status_code == 200
    approved_data = feedback_resp.json()
    table_names = {t["table_name"] for t in approved_data["selected_tables"]}
    assert table_names == {"orders", "order_items"}
