# SchemaLink: High-Precision Schema RAG & Discovery Engine
## Technical Design Specification

**Document Type:** Technical Architecture and System Design  
**Project Name:** SchemaLink  
**Status:** Approved  
**Version:** 1.0  
**Target Repository:** `/Users/muhamadtalebi/Developer/SchemaLink`

---

## 1. Executive Summary

### 1.1 Problem Statement
In enterprise environments with large, complex multi-database ecosystems (hundreds or thousands of tables and tens of thousands of columns), attempting to build Text-to-SQL or database Q&A systems presents major pitfalls:
1. **Raw Data Vectorization Failure:** Embedding actual database records into a vector database is cost-prohibitive, creates massive security and privacy risks, and fails to handle analytical aggregations (e.g., `SUM`, `AVG`, `GROUP BY`) across millions of rows.
2. **Context Window Saturation:** Providing entire database DDLs to LLMs exceeds context windows, dramatically increases token costs, and induces hallucinations.
3. **Namespace & Column Ambiguity:** Identical or similar column names (e.g., `created_at`, `status`, `id`, `amount`) across dozens of tables confuse retrieval and generation models.
4. **Broken Join Paths:** Independent table retrieval often selects endpoints (e.g., `customers` and `products`) but misses necessary bridge tables (e.g., `orders` and `order_items`).

### 1.2 Proposed Solution: SchemaLink
**SchemaLink** is an independent, high-precision **Schema RAG Engine**. Instead of embedding business rows, it indexes structured schema metadata and human-injected business knowledge into a multi-layered hybrid index.

At query time, SchemaLink:
1. Routes the natural language query to the relevant target database(s).
2. Performs bidirectional hybrid retrieval across table and column documents.
3. Traverses an in-memory relationship graph to discover and inject valid join paths and intermediate bridge tables.
4. Operates in either **Autonomous Mode** (fully automated filtering) or **Human-in-the-Loop (HITL) Mode** (interactive inspection and feedback).
5. Emits a compact, validated schema context package directly to any downstream Query Generation Agent.
6. Learns from human feedback using an exemplar memory store to improve future retrieval accuracy.

---

## 2. Core Design Principles & Scope

### 2.1 Scope Boundaries
* **In Scope:**
  * Multi-database connection and automated metadata introspection.
  * User injection of business logic, semantic synonyms, and virtual/logical foreign keys.
  * Multi-granularity document modeling (Database, Table, Column, Relationship).
  * Hybrid retrieval (Dense Vector + BM25 sparse vectors) with Reciprocal Rank Fusion (RRF).
  * Graph-based join path and bridge table discovery.
  * Dual-mode execution (Autonomous vs. Human-in-the-Loop).
  * Feedback storage and dynamic exemplar-based retrieval boosting.
  * Structured schema context output contract for downstream agents.
* **Out of Scope:**
  * Direct SQL query generation or execution against operational data (delegated to the downstream agent).
  * Vectorizing or storing raw database row records.
  * Modifying source database schemas or executing DDL/DML.

### 2.2 Guiding Architectural Principles
1. **Decoupled Architecture:** Schema retrieval must function as an independent service, decoupled from query synthesis.
2. **Zero Row Vectorization:** The operational database remains the sole source of truth for business data; the vector store stores metadata and domain knowledge only.
3. **Multi-Granular Decomposition:** Table-level discovery and column-level metric matching are distinct operations.
4. **Deterministic Join Integrity:** Join paths are resolved via deterministic graph algorithms (NetworkX) over physical foreign keys and validated logical relations, not LLM guesses.
5. **Continuous Learning:** User corrections in HITL mode directly reinforce future retrieval via exemplar memory without requiring model fine-tuning.

---

## 3. Technology Stack

| Layer | Selected Technology | Architectural Rationale |
| :--- | :--- | :--- |
| **Agent & Workflow Engine** | **LangGraph** | Native support for stateful workflows, checkpoints, and Human-in-the-Loop `interrupt` / `resume` execution. |
| **Metadata Introspection** | **SQLAlchemy** | Vendor-agnostic dialect abstraction supporting PostgreSQL, MySQL, SQLite, MSSQL, Oracle, and Snowflake. |
| **Hybrid Search & Vector Store**| **Qdrant** | Unified engine supporting dense vectors, native BM25 sparse vectors, and payload metadata filtering. Embedded mode for local development; server mode for production. |
| **Graph Relationship Engine** | **NetworkX** | Lightweight, high-speed in-memory directed multigraph for finding shortest and k-shortest join paths and bridge tables. |
| **Embeddings** | **FastEmbed (`BAAI/bge-m3` or `bge-small-en-v1.5`)** | Lightweight ONNX runtime embeddings without heavy PyTorch dependencies; high performance on CPU/GPU. |
| **SQL Validation & Inspection**| **SQLGlot** | Robust SQL AST parsing, validation of schema references, and dialect transpilation. |
| **API & Data Validation** | **FastAPI + Pydantic v2** | High-performance asynchronous REST API with strict request/response data contracts. |

---

## 4. System Architecture & Components

```
┌────────────────────────────────────────────────────────────────────────┐
│                          SchemaLink Engine                             │
│                                                                        │
│   ┌─────────────────────────┐            ┌─────────────────────────┐   │
│   │   Database Connectors   │            │ Business Logic Registry │   │
│   │  (SQLAlchemy Inspector) │            │  (Custom Rules / Joins) │   │
│   └────────────┬────────────┘            └────────────┬────────────┘   │
│                │                                      │                │
│                └──────────────────┬───────────────────┘                │
│                                   ▼                                    │
│                    ┌────────────────────────────┐                      │
│                    │ Metadata Normalization &   │                      │
│                    │ Document Generator         │                      │
│                    └──────────────┬─────────────┘                      │
│                                   ▼                                    │
│       ┌───────────────────────────────────────────────────────┐        │
│       │ Storage & Indexing                                    │        │
│       │  • DB Index (Qdrant)                                  │        │
│       │  • Table Index (Dense + BM25)                         │        │
│       │  • Column Index (Dense + BM25)                        │        │
│       │  • Exemplar Memory Index (Past Feedback)              │        │
│       │  • In-Memory Relationship Graph (NetworkX)            │        │
│       └───────────────────────────┬───────────────────────────┘        │
│                                   ▼                                    │
│   User Question ───────► ┌─────────────────────────┐                   │
│                          │ Query Router & Planner  │                   │
│                          └────────────┬────────────┘                   │
│                                       ▼                                │
│                          ┌─────────────────────────┐                   │
│                          │ Bidirectional Retrieval │                   │
│                          │ (Table-first + Col-1st) │                   │
│                          └────────────┬────────────┘                   │
│                                       ▼                                │
│                          ┌─────────────────────────┐                   │
│                          │ Graph Join Resolver     │                   │
│                          │ (Bridge Table Discovery)│                   │
│                          └────────────┬────────────┘                   │
│                                       ▼                                │
│                          ┌─────────────────────────┐                   │
│                          │ Mode Selection Switch   │                   │
│                          └─────┬─────────────┬─────┘                   │
│                                │             │                         │
│             Autonomous Mode    │             │  HITL Mode              │
│             (Direct Context)   │             ▼                         │
│                                │      ┌──────────────┐                 │
│                                │      │ LangGraph    │                 │
│                                │      │ Interrupt    │                 │
│                                │      └──────┬───────┘                 │
│                                │             │ User Feedback           │
│                                │             ▼                         │
│                                │      ┌──────────────┐                 │
│                                │      │ Exemplar &   │                 │
│                                │      │ Graph Boost  │                 │
│                                │      └──────┬───────┘                 │
│                                └──────┬──────┘                         │
│                                       ▼                                │
│                     [ Curated Schema Context Package ]                 │
└───────────────────────────────────────┬────────────────────────────────┘
                                        │
                                        ▼
                     ┌────────────────────────────────────┐
                     │ Downstream Query Generator Agent   │
                     │ (Generates SQL & Queries DB)       │
                     └────────────────────────────────────┘
```

---

## 5. Detailed Component Specifications

### 5.1 Metadata Extraction & Normalization
* **Connector Interface (`src/connectors/base.py`):** Abstract class defining methods:
  * `get_database_metadata()`
  * `get_tables()`
  * `get_columns(table_name)`
  * `get_primary_keys(table_name)`
  * `get_foreign_keys(table_name)`
  * `get_table_comments(table_name)` / `get_column_comments(table_name, column_name)`
* **Normalized Metadata Model (`src/models/metadata.py`):**
  * Preserves exact physical identifiers without destructive normalization.
  * Encapsulates `database_id`, `schema_name`, `table_name`, `columns` (name, type, nullable, PK), and `foreign_keys`.

### 5.2 Business Logic & Semantic Injection Layer
Allows domain experts to enrich raw physical database structures via API or configuration:
1. **Database Annotations:**
   * Business domain classification (e.g., `["e-commerce", "logistics", "payments"]`).
   * Description of the database's business scope.
2. **Table Annotations:**
   * Business synonyms (e.g., `tbl_ord_mstr` $\rightarrow$ `["orders", "customer purchases", "sales"]`).
   * Default business rules (e.g., "Filter out `is_test = true` and `deleted_at IS NOT NULL`").
3. **Column Annotations:**
   * Business definitions & calculation formulas (e.g., `orders.rev_net` $\rightarrow$ "Gross amount minus returns and tax").
   * Business abbreviations and metric names.
4. **Logical Relationship Injection:**
   * Defines virtual joins when physical foreign keys are omitted in the DB schema:
     ```json
     {
       "source_table": "orders",
       "source_column": "customer_code",
       "target_table": "customers",
       "target_column": "code",
       "relationship_type": "virtual_foreign_key",
       "confidence": 0.95
     }
     ```

### 5.3 Multi-Granular Document Generation
The document builder transforms raw and enriched metadata into 4 indexable structures:

#### Table Document
```json
{
  "document_id": "sales_db.public.orders",
  "document_type": "table",
  "database_id": "sales_db",
  "schema": "public",
  "table_name": "orders",
  "description": "Customer purchase orders and fulfillment status",
  "business_terms": ["orders", "sales transactions", "purchases"],
  "column_names": ["id", "customer_id", "total_amount", "order_date", "status"],
  "content_hash": "a1b2c3d4..."
}
```

#### Column Document
```json
{
  "document_id": "sales_db.public.orders.total_amount",
  "document_type": "column",
  "database_id": "sales_db",
  "table_name": "orders",
  "column_name": "total_amount",
  "data_type": "numeric(12,2)",
  "is_primary_key": false,
  "description": "Total monetary amount charged including taxes and shipping",
  "business_terms": ["revenue", "sales volume", "order total", "gross spending"],
  "parent_table_description": "Customer purchase orders",
  "content_hash": "e5f6g7h8..."
}
```

---

## 6. Retrieval & Resolution Engine

### 6.1 Multi-Database Routing
* Queries are first evaluated against the **Database Index**.
* Matches question intent against database descriptions and domain tags.
* Emits target `database_id` to constrain subsequent searches, preventing cross-database noise.

### 6.2 Bidirectional Hybrid Retrieval
Retrieval runs two parallel paths merged using Reciprocal Rank Fusion (RRF):
1. **Table-First Retrieval:**
   * Hybrid search (Dense embedding + BM25) over Table documents.
   * Finds tables whose descriptions or business names match the query.
   * Fetches columns associated with these candidate tables.
2. **Column-First Retrieval:**
   * Hybrid search across all Column documents in the target database.
   * Matches specific metrics, dimensions, and attributes (e.g., "net revenue", "postal code").
   * Promotes the parent tables of high-scoring columns.
3. **RRF Candidate Merging:**
   * RRF score formula: $RRF(d) = \sum_{m \in M} \frac{1}{60 + rank_m(d)}$.
   * Merges and de-duplicates candidate tables and columns while tracking provenance.

### 6.3 Graph Join Resolution & Bridge Table Discovery
1. **Graph Construction:**
   * In-memory NetworkX `MultiDiGraph`.
   * Nodes: Tables.
   * Edges: Physical foreign keys (weight: 1.0) + User-injected virtual joins (weight: 0.95) + Discovered relationships (weight: $\le 0.8$).
2. **Bridge Discovery:**
   * When retrieved candidate tables are not directly connected (e.g., `customers` and `products`), the resolver computes the all-pairs shortest paths.
   * Intermediate bridge tables (e.g., `orders`, `order_items`) and join conditions are automatically injected into the schema context.

---

## 7. Execution Modes: Autonomous vs. Human-in-the-Loop (HITL)

### 7.1 Mode A: Autonomous Mode
* High-confidence candidate tables and columns above a dynamic threshold are auto-selected.
* Join paths are resolved deterministically.
* Produces final **Curated Schema Context Package** immediately.

### 7.2 Mode B: Human-in-the-Loop (HITL) Mode
* Implemented using **LangGraph `interrupt`**.
* The execution graph pauses and emits a review payload:
  ```json
  {
    "session_id": "sess_102938",
    "query": "Total revenue per branch last quarter",
    "status": "awaiting_human_feedback",
    "candidate_database": "sales_db",
    "candidate_tables": [
      {"table": "branches", "confidence": 0.94, "selected": true, "reason": "matches dimension 'branch'"},
      {"table": "orders", "confidence": 0.89, "selected": true, "reason": "matches metric 'revenue'"},
      {"table": "branch_audits", "confidence": 0.42, "selected": false, "reason": "low lexical match"}
    ],
    "candidate_columns": [
      {"table": "branches", "column": "branch_name", "selected": true},
      {"table": "orders", "column": "total_amount", "selected": true},
      {"table": "orders", "column": "order_date", "selected": true}
    ],
    "suggested_joins": [
      {
        "source": "orders.branch_id",
        "target": "branches.id",
        "selected": true,
        "type": "foreign_key"
      }
    ]
  }
  ```
* **User Feedback Actions:**
  * Toggle table/column selections (include/exclude).
  * Add custom missing tables/columns.
  * Confirm or override join paths.
* **Resume & Continuous Learning:**
  * Client calls `/api/v1/retrieval/feedback` or resumes LangGraph state.
  * Approved context is forwarded to the downstream Query Agent.
  * The approved selection is stored in the **Exemplar Memory Store** to boost similar future queries.

---

## 8. Output Contract: Curated Schema Context Package

SchemaLink outputs a strictly typed JSON payload for the downstream Query Generator Agent:

```json
{
  "database_id": "sales_db",
  "engine_type": "postgresql",
  "query": "Total revenue per branch last quarter",
  "selected_tables": [
    {
      "table_name": "branches",
      "description": "Company physical branch locations",
      "columns": [
        {"name": "id", "type": "bigint", "is_primary_key": true},
        {"name": "branch_name", "type": "varchar(255)", "is_primary_key": false}
      ]
    },
    {
      "table_name": "orders",
      "description": "Customer purchase orders",
      "columns": [
        {"name": "id", "type": "bigint", "is_primary_key": true},
        {"name": "branch_id", "type": "bigint", "is_primary_key": false},
        {"name": "total_amount", "type": "numeric(12,2)", "is_primary_key": false},
        {"name": "order_date", "type": "timestamp", "is_primary_key": false}
      ]
    }
  ],
  "join_paths": [
    {
      "source_table": "orders",
      "source_column": "branch_id",
      "target_table": "branches",
      "target_column": "id",
      "type": "physical_foreign_key"
    }
  ],
  "business_rules": [
    "Always filter orders with status = 'COMPLETED'",
    "Revenue is calculated from orders.total_amount"
  ],
  "provenance": {
    "mode": "hitl_approved",
    "retrieval_strategy": "bidirectional_hybrid_rrf",
    "confidence_score": 0.96
  }
}
```

---

## 9. API Specification

### Database Management & Introspection
* `POST /api/v1/databases`: Register a database connection URI and options.
* `POST /api/v1/databases/{database_id}/index`: Run full schema introspection and indexing.
* `POST /api/v1/databases/{database_id}/sync`: Incremental sync detecting schema diffs via content hashes.

### Business Logic Injection
* `POST /api/v1/databases/{database_id}/annotations`: Add or update domain annotations, synonyms, table rules, and virtual relationships.
* `GET /api/v1/databases/{database_id}/annotations`: Retrieve all registered business annotations.

### Schema Retrieval & HITL Workflow
* `POST /api/v1/retrieval/schema`: Run schema retrieval. Accepts `query`, `mode` (`autonomous` or `hitl`), and `thresholds`.
* `POST /api/v1/retrieval/{session_id}/feedback`: Submit human review modifications and resume workflow.

---

## 10. Repository Directory Structure

```text
SchemaLink/
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-11-11-schemalink-design.md
├── src/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── databases.py
│   │   │   ├── annotations.py
│   │   │   └── retrieval.py
│   │   └── server.py
│   ├── connectors/
│   │   ├── base.py
│   │   ├── postgres.py
│   │   ├── mysql.py
│   │   ├── sqlite.py
│   │   └── factory.py
│   ├── models/
│   │   ├── metadata.py
│   │   ├── documents.py
│   │   └── context.py
│   ├── registry/
│   │   └── business_logic.py
│   ├── indexing/
│   │   ├── document_builder.py
│   │   ├── hybrid_store.py
│   │   └── exemplar_store.py
│   ├── graph/
│   │   ├── schema_graph.py
│   │   └── path_finder.py
│   ├── workflow/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── graph.py
│   └── utils/
│       └── hashing.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── pyproject.toml
├── spec.md
└── README.md
```

---

## 11. Implementation Phasing

1. **Phase 1: Database Catalog Introspection & Business Registry**
   * SQLAlchemy generic connector + SQLite / PostgreSQL testing fixtures.
   * Business Logic Registry for injecting domain metadata, column formulas, and virtual foreign keys.
2. **Phase 2: Hybrid Indexing & Document Builders**
   * Multi-granularity document modeling (Database, Table, Column).
   * FastEmbed embedding generation + Qdrant hybrid storage (dense + BM25).
3. **Phase 3: Bidirectional Retrieval & NetworkX Join Resolver**
   * Table-first and Column-first retrieval merged via RRF.
   * Shortest-path join discovery with bridge table injection.
4. **Phase 4: LangGraph Workflow & HITL Loop**
   * Dual-mode state machine (Autonomous vs. Interrupt/Resume).
   * Feedback recording and Exemplar Memory index.
5. **Phase 5: FastAPI REST Endpoints & End-to-End Testing**
   * Expose all registration, indexing, retrieval, and feedback endpoints.
   * Integration tests with multi-table complex schemas.
