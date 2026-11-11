"""Test database fixture with realistic relational schema and enum values."""

import sqlite3
from pathlib import Path


def create_ecommerce_test_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Branches table
    cursor.execute("""
    CREATE TABLE branches (
        id INTEGER PRIMARY KEY,
        branch_name TEXT NOT NULL,
        state TEXT NOT NULL,
        city TEXT NOT NULL,
        created_at TEXT
    )
    """)

    # Customers table
    cursor.execute("""
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        tier TEXT NOT NULL,
        created_at TEXT
    )
    """)

    # Products table
    cursor.execute("""
    CREATE TABLE products (
        id INTEGER PRIMARY KEY,
        sku TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_price REAL NOT NULL
    )
    """)

    # Orders table
    cursor.execute("""
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL,
        branch_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        total_amount REAL NOT NULL,
        order_date TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers (id),
        FOREIGN KEY (branch_id) REFERENCES branches (id)
    )
    """)

    # Order Items table (bridge between orders and products)
    cursor.execute("""
    CREATE TABLE order_items (
        id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        line_total REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders (id),
        FOREIGN KEY (product_id) REFERENCES products (id)
    )
    """)

    # Sample data for low-cardinality enum profiling
    cursor.executemany(
        "INSERT INTO branches (id, branch_name, state, city) VALUES (?, ?, ?, ?)",
        [
            (1, "Downtown SF", "CA", "San Francisco"),
            (2, "LA Central", "CA", "Los Angeles"),
            (3, "NYC Midtown", "NY", "New York"),
        ],
    )

    cursor.executemany(
        "INSERT INTO customers (id, name, email, tier) VALUES (?, ?, ?, ?)",
        [
            (1, "Alice Smith", "alice@example.com", "GOLD"),
            (2, "Bob Jones", "bob@example.com", "PLATINUM"),
            (3, "Charlie Brown", "charlie@example.com", "SILVER"),
        ],
    )

    cursor.executemany(
        "INSERT INTO products (id, sku, title, category, unit_price) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "SKU-001", "MacBook Pro", "Electronics", 1999.99),
            (2, "SKU-002", "iPhone 15", "Electronics", 999.99),
        ],
    )

    cursor.executemany(
        "INSERT INTO orders (id, customer_id, branch_id, status, total_amount, order_date) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, 1, 1, "COMPLETED", 1999.99, "2024-01-15"),
            (2, 2, 2, "COMPLETED", 999.99, "2024-02-10"),
            (3, 3, 1, "PENDING", 450.00, "2024-03-01"),
        ],
    )

    cursor.executemany(
        "INSERT INTO order_items (id, order_id, product_id, quantity, line_total) VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, 1, 1, 1999.99),
            (2, 2, 2, 1, 999.99),
        ],
    )

    conn.commit()
    conn.close()
