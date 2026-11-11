"""Unit tests for catalog introspection, profiler, and business logic registry."""

import pytest

from src.catalog.profiler import CategoricalProfiler
from src.connectors.base import SQLAlchemyConnector
from src.registry.business_logic import (
    BusinessLogicRegistry,
    ColumnAnnotation,
    TableAnnotation,
    VirtualForeignKey,
)
from tests.fixtures.sample_db import create_ecommerce_test_db


@pytest.fixture
def test_db_path(tmp_path):
    db_file = tmp_path / "test_ecommerce.db"
    create_ecommerce_test_db(str(db_file))
    return str(db_file)


def test_connector_introspection(test_db_path):
    uri = f"sqlite:///{test_db_path}"
    connector = SQLAlchemyConnector("sales_db", uri)
    assert connector.test_connection() is True

    db_info = connector.introspect()
    assert db_info.database_id == "sales_db"
    table_names = {t.table_name for t in db_info.tables}
    assert "orders" in table_names
    assert "branches" in table_names
    assert "customers" in table_names
    assert "order_items" in table_names
    assert "products" in table_names

    # Check orders foreign keys
    orders_table = next(t for t in db_info.tables if t.table_name == "orders")
    fk_targets = {fk.target_table for fk in orders_table.foreign_keys}
    assert "customers" in fk_targets
    assert "branches" in fk_targets


def test_categorical_profiler(test_db_path):
    uri = f"sqlite:///{test_db_path}"
    connector = SQLAlchemyConnector("sales_db", uri)
    db_info = connector.introspect()

    profiler = CategoricalProfiler(connector, max_distinct=10)
    profiles = profiler.profile_database(db_info)

    # Status column in orders should be profiled
    assert "orders.status" in profiles
    assert set(profiles["orders.status"].distinct_values) == {"COMPLETED", "PENDING"}

    # State column in branches should be profiled
    assert "branches.state" in profiles
    assert set(profiles["branches.state"].distinct_values) == {"CA", "NY"}


def test_business_logic_registry(tmp_path):
    reg = BusinessLogicRegistry(storage_dir=str(tmp_path))

    reg.add_table_annotation(
        "sales_db",
        TableAnnotation(
            table_name="orders",
            business_synonyms=["purchases", "sales transactions"],
            business_rules=["Only count status = 'COMPLETED'"],
        ),
    )

    reg.add_column_annotation(
        "sales_db",
        ColumnAnnotation(
            table_name="orders",
            column_name="total_amount",
            business_synonyms=["gross revenue", "sales volume"],
            calculation_formula="sum(orders.total_amount)",
        ),
    )

    reg.add_virtual_foreign_key(
        "sales_db",
        VirtualForeignKey(
            source_table="orders",
            source_column="customer_code",
            target_table="customers",
            target_column="code",
        ),
    )

    ann = reg.get_database_annotation("sales_db")
    assert "orders" in ann.tables
    assert "orders.total_amount" in ann.columns
    assert len(ann.virtual_foreign_keys) == 1
