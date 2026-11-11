# SchemaLink: High-Precision Schema RAG & Discovery Engine
## Technical Design Specification

**Document Type:** Technical Architecture and System Design  
**Project Name:** SchemaLink  
**Status:** Approved  
**Version:** 2.0 (LLM & RAG Engineering Edition)  
**Target Repository:** `/Users/muhamadtalebi/Developer/SchemaLink`

---

## 1. Executive Summary

### 1.1 Problem Statement
In enterprise environments with large, complex multi-database ecosystems (hundreds of tables and tens of thousands of columns), standard approaches to database Q&A and Text-to-SQL fail:
1. **Raw Data Vectorization Failure:** Embedding actual database records into a vector database is cost-prohibitive, creates massive security and privacy risks, and cannot compute exact analytical aggregations (`SUM`, `AVG`, `GROUP BY`) across millions of rows.
2. **Context Window Saturation:** Providing entire database DDLs to LLMs exceeds context windows, explodes token costs, and induces hallucinations.
3. **Namespace & Column Ambiguity:** Identical or generic column names (`created_at`, `status`, `id`, `amount`) across dozens of tables cause severe lexical collisions and retrieval noise.
4. **Broken Join Paths:** Independent table retrieval often retrieves endpoints (e.g., `customers` and `products`) but drops necessary intermediate bridge tables (e.g., `orders` and `order_items`).
5. **Filter Value Mismatches:** Queries contain natural language filter values (e.g., "California" or "Active") that do not lexically match raw database enum literals (e.g., `'CA'` or `1`), resulting in zero-row SQL outputs.

### 1.2 Proposed Solution: SchemaLink
**SchemaLink** is an independent, high-precision **Schema RAG Engine**. Instead of embedding business records, it indexes structured database schema metadata, low-cardinality categorical profiles, and human-injected business knowledge into a multi-layered hybrid index.

At query time, SchemaLink:
1. Performs semantic intent decomposition (extracting measures, dimensions, filters, and schema hints).
2. Routes the query to target database(s) using a Database Profile Index.
3. Executes bidirectional hybrid retrieval across table and column documents (Dense + BM25 merged via RRF).
4. Employs a 2nd-stage Cross-Encoder Reranker to filter out generic column false-positives.
5. Traverses an in-memory relationship graph (NetworkX) to discover deterministic join paths and inject intermediate bridge tables.
6. Enforces Token Budgeting and Compact Serialization (Markdown DDL or JSON) to minimize LLM token consumption.
7. Operates in either **Autonomous Mode** (fully automated filtering) or **Human-in-the-Loop (HITL) Mode** (interactive inspection and feedback via LangGraph).
8. Emits a curated, validated schema context package directly to any downstream Query Generation Agent or LLM via REST, MCP, Python SDK, or Framework Tools.
9. Learns from human feedback using an Exemplar Memory Store to boost future retrieval accuracy.

---

## 2. Core Design Principles & Scope

### 2.1 Scope Boundaries
* **In Scope:**
  * Multi-database connection and automated metadata introspection (PostgreSQL, MySQL, SQLite, MSSQL, Snowflake).
  * Low-cardinality categorical value profiling (enum literals and code lists).
  * User injection of business logic, semantic synonyms, and virtual/logical foreign keys.
  * Multi-granularity document modeling (Database, Table, Column, Categorical).
  * Query intent decomposition and schema-oriented query expansion.
  * Hybrid retrieval (Dense Vector + BM25 sparse vectors) with Reciprocal Rank Fusion (RRF).
  * 2nd-stage Cross-Encoder Reranking for high-precision filtering.
  * Graph-based join path and bridge table discovery.
  * Token-budgeted context formatting (Compact DDL / Structured JSON).
  * Dual-mode execution (Autonomous vs. Human-in-the-Loop via LangGraph).
  * Continuous learning via Exemplar Memory and relationship graph reinforcement.
  * Downstream agent interfaces (REST, MCP Server, LangChain/LlamaIndex tools, Python SDK).
  * Security defenses against metadata prompt injection and PII leakage.
* **Out of Scope:**
  * Direct SQL query generation or execution against operational data (delegated to the downstream agent).
  * Vectorizing or storing raw database row records.
  * Modifying source database schemas or executing DDL/DML.

### 2.2 Guiding Architectural Principles
1. **Decoupled Architecture:** Schema retrieval operates as a standalone service, independent of SQL generation.
2. **Zero Row Vectorization:** Operational databases remain the sole source of truth for business data; the vector database indexes schema metadata, categorical values, and domain knowledge only.
3. **Multi-Granular Decomposition:** Table discovery and column-level metric matching are treated as distinct, bidirectional search operations.
4. **Deterministic Join Integrity:** Join paths are resolved via deterministic graph algorithms over physical foreign keys and validated logical relations, avoiding LLM hallucinations.
5. **Token Efficiency:** Context serializers maximize information density while minimizing token footprint through intelligent column pruning.
6. **Continuous Learning:** User corrections in HITL mode directly reinforce future retrieval via exemplar memory without model fine-tuning.

---

## 3. Technology Stack

| Layer | Selected Technology | Architectural Rationale |
| :--- | :--- | :--- |
| **Agent & Workflow Engine** | **LangGraph** | Stateful workflow orchestration, checkpoint persistence, and native Human-in-the-Loop `interrupt` / `resume` execution. |
| **Metadata Introspection** | **SQLAlchemy** | Dialect-agnostic catalog inspection for PostgreSQL, MySQL, SQLite, MSSQL, Oracle, and Snowflake. |
| **Hybrid Search & Vector Store**| **Qdrant** | Unified engine supporting dense vectors, BM25 sparse vectors, and payload metadata filtering. Supports embedded local mode and containerized production deployment. |
| **Graph Relationship Engine** | **NetworkX** | Lightweight in-memory directed multigraph for computing shortest join paths, Steiner minimal trees, and bridge table injection. |
| **Embeddings** | **FastEmbed (`BAAI/bge-m3` or `bge-small-en-v1.5`)** | Fast ONNX runtime embeddings without PyTorch overhead; high throughput on CPU and GPU. |
| **2nd-Stage Reranking** | **FlashRank / `bge-reranker-base`** | Ultralight cross-encoder for re-scoring top candidate tables and columns against query intent. |
| **SQL Validation & Inspection**| **SQLGlot** | Robust SQL AST parsing, validation of schema references, and dialect transpilation. |
| **Context Serialization** | **Tiktoken / Custom Tokenizer** | Precise token budgeting and compaction to prevent context window overflow. |
| **API & Data Validation** | **FastAPI + Pydantic v2** | High-performance asynchronous REST API with strict request/response data contracts. |
| **Model Context Protocol** | **mcp-python SDK** | Native MCP server implementation for Cursor, Claude Desktop, and modern AI environments. |

---

## 4. End-to-End System Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 SchemaLink Engine                                      │
│                                                                                        │
│   ┌─────────────────────────┐   ┌─────────────────────────┐   ┌────────────────────┐   │
│   │   Database Connectors   │   │ Business Logic Registry │   │ Categorical Value  │   │
│   │  (SQLAlchemy Inspector) │   │ (Custom Rules / Joins)  │   │ Profiler (Enums)   │   │
│   └────────────┬────────────┘   └────────────┬────────────┘   └─────────┬──────────┘   │
│                │                             │                          │              │
│                └──────────────────────┬──────┴──────────────────────────┘              │
│                                       ▼                                                │
│                      ┌─────────────────────────────────┐                               │
│                      │ Metadata Normalization Engine & │                               │
│                      │ Multi-Document Generator        │                               │
│                      └────────────────┬────────────────┘                               │
│                                       ▼                                                │
│         ┌─────────────────────────────────────────────────────────────┐                │
│         │ Hybrid Storage & Relationship Topology                      │                │
│         │  • Database Index (Qdrant: Domain & DB Profiles)            │                │
│         │  • Table Index (Qdrant: Dense + BM25)                       │                │
│         │  • Column Index (Qdrant: Dense + BM25 + Enums)              │                │
│         │  • Exemplar Memory Store (Qdrant: Query ↔ Approved Schema)  │                │
│         │  • In-Memory Relationship Graph (NetworkX MultiDiGraph)     │                │
│         └─────────────────────────────┬───────────────────────────────┘                │
│                                       ▼                                                │
│   User Question ───────────► ┌─────────────────────────────────┐                       │
│                              │ Query Intent & Decomposition    │                       │
│                              │ (Measures, Dimensions, Filters) │                       │
│                              └────────────────┬────────────────┘                       │
│                                       ▼                                                │
│                              ┌─────────────────────────────────┐                       │
│                              │ Multi-DB Routing Layer          │                       │
│                              └────────────────┬────────────────┘                       │
│                                       ▼                                                │
│                              ┌─────────────────────────────────┐                       │
│                              │ Bidirectional Hybrid Retrieval  │                       │
│                              │ (Table-first + Column-first)    │                       │
│                              └────────────────┬────────────────┘                       │
│                                       ▼                                                │
│                              ┌─────────────────────────────────┐                       │
│                              │ RRF Candidate Fusion &          │                       │
│                              │ 2nd-Stage Cross-Encoder Rerank  │                       │
│                              └────────────────┬────────────────┘                       │
│                                       ▼                                                │
│                              ┌─────────────────────────────────┐                       │
│                              │ Graph Join Path & Bridge Finder │                       │
│                              └────────────────┬────────────────┘                       │
│                                       ▼                                                │
│                              ┌─────────────────────────────────┐                       │
│                              │ Mode Selection Switch           │                       │
│                              └───────┬─────────────────┬───────┘                       │
│                                      │                 │                               │
│                   Autonomous Mode    │                 │  HITL Mode                    │
│                   (Direct Context)   │                 ▼                               │
│                                      │          ┌──────────────┐                       │
│                                      │          │ LangGraph    │                       │
│                                      │          │ Interrupt    │                       │
│                                      │          └──────┬───────┘                       │
│                                      │                 │ User Feedback                 │
│                                      │                 ▼                               │
│                                      │          ┌──────────────┐                       │
│                                      │          │ Exemplar &   │                       │
│                                      │          │ Graph Boost  │                       │
│                                      │          └──────┬───────┘                       │
│                                      └─────────┬───────┘                               │
│                                                ▼                                       │
│                              ┌──────────────────────────────────┐                      │
│                              │ Token Budgeting & Compactor      │                      │
│                              │ (Compact DDL / Structured JSON)  │                      │
│                              └─────────────────┬────────────────┘                      │
│                                                ▼                                       │
│                                [ Curated Schema Context Package ]                      │
└────────────────────────────────────────────────┬───────────────────────────────────────┘
                                                 │
                                                 ▼
             ┌───────────────────────────────────────────────────────────────────┐
             │ Downstream Query Generator Agent / LLM                            │
             │   • Consumption: REST API / MCP Server / Python SDK / Tools       │
             │   • Generates SQL using strictly the curated schema context       │
             │   • Validates AST and executes on operational database            │
             └───────────────────────────────────────────────────────────────────┘
```

---

## 5. Detailed Component Specifications

### 5.1 Metadata Extraction & Categorical Profiler
* **Database Connector (`src/connectors/base.py`):**
  * Generic SQLAlchemy inspector capturing table names, schema names, column types, nullability, primary keys, foreign keys, and comments.
* **Categorical Value Profiler (`src/catalog/profiler.py`):**
  * Discovers low-cardinality categorical columns ($\le 50$ distinct values, e.g., `status`, `country_code`, `tier`).
  * Gathers distinct value sets and stores them in column metadata.
  * When a user question references a natural language label (e.g., "pending transactions"), the column index matches against the enum profile (`['PENDING', 'APPROVED', 'CANCELLED']`), solving literal mismatch errors.

### 5.2 Business Logic & Semantic Injection Layer
Domain experts enrich physical database schemas with business logic via API (`src/registry/business_logic.py`):
1. **Database Level:**
   * Business domain classification (e.g., `["sales", "e-commerce", "fulfillment"]`).
   * High-level narrative description of the database's business purpose.
2. **Table Level:**
   * Business synonyms (e.g., `tbl_ord_hdr` $\rightarrow$ `["orders", "customer purchases", "sales receipts"]`).
   * Mandatory business rules (e.g., "Exclude test accounts where `is_test = true`").
3. **Column Level:**
   * Metric definitions & calculations (e.g., `orders.net_amt` $\rightarrow$ "Gross total minus discounts and refunds").
   * Synonyms and acronyms (e.g., `arr` $\rightarrow$ "Annual Recurring Revenue").
4. **Logical Relationship Injection:**
   * Defines virtual joins when physical foreign keys are absent:
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
The document builder transforms raw schema and business knowledge into 4 indexable structures:

#### Database Document
```json
{
  "document_id": "db_sales",
  "document_type": "database",
  "database_id": "sales_db",
  "domains": ["sales", "orders", "inventory", "customers"],
  "description": "Primary transactional database for e-commerce orders and customer accounts",
  "content_hash": "a1b2c3..."
}
```

#### Table Document
```json
{
  "document_id": "sales_db.public.orders",
  "document_type": "table",
  "database_id": "sales_db",
  "schema": "public",
  "table_name": "orders",
  "description": "Customer purchase transactions and order fulfillment state",
  "business_terms": ["orders", "sales", "purchases", "transactions"],
  "business_rules": ["Filter orders with status = 'COMPLETED' for revenue metrics"],
  "column_names": ["id", "customer_id", "total_amount", "status", "created_at"],
  "content_hash": "d4e5f6..."
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
  "business_terms": ["revenue", "order value", "sales total", "gross spending"],
  "categorical_values": [],
  "parent_table_description": "Customer purchase transactions",
  "content_hash": "g7h8i9..."
}
```

---

## 6. Retrieval, Reranking & Graph Resolution

### 6.1 Query Intent Decomposition
Before vector lookup, a lightweight pre-processor extracts:
* **Measures / Metrics:** e.g., "total revenue", "average order value".
* **Dimensions:** e.g., "branch", "customer tier", "date".
* **Filter Conditions & Literals:** e.g., "California", "last quarter", "active".
* **Schema Hints:** Extracted entity keywords used for dense + BM25 keyword matching.

### 6.2 Multi-Database Routing
1. Evaluates query against the **Database Index**.
2. Ranks database profiles by cosine similarity and domain match.
3. Selects the target `database_id` to constrain subsequent searches, eliminating cross-database namespace collision.

### 6.3 Bidirectional Hybrid Retrieval & Reranking
1. **Parallel Retrieval Paths:**
   * **Table-First:** Dense vector + BM25 search over Table Documents $\rightarrow$ yields top candidate tables.
   * **Column-First:** Dense vector + BM25 search over Column Documents (matching metrics, dimensions, and categorical values) $\rightarrow$ promotes parent tables of high-scoring columns.
2. **Reciprocal Rank Fusion (RRF):**
   * Combines rankings: $RRF(d) = \sum_{m \in M} \frac{1}{60 + rank_m(d)}$.
3. **2nd-Stage Cross-Encoder Reranker (`FlashRank`):**
   * Evaluates `(query, table_summary)` pairs for top-30 candidates to eliminate generic lexical collisions.
   * Produces calibrated confidence scores for candidate tables and columns.

### 6.4 Graph Join Path Resolution & Bridge Table Discovery
1. **NetworkX Relationship Graph:**
   * Nodes: Tables.
   * Edges: Directed links representing physical foreign keys (weight: 1.0) and user-injected virtual joins (weight: 0.95).
2. **Bridge Discovery Algorithm:**
   * Given candidate tables $T = \{t_1, t_2, \dots, t_k\}$, finds the minimum connecting subgraph (approximate Steiner Tree / all-pairs shortest paths).
   * Identifies missing intermediate bridge tables (e.g., connects `customers` and `products` via `orders` and `order_items`).
   * Automatically adds bridge tables and join conditions to the schema context.

---

## 7. Dual Execution Modes: Autonomous vs. HITL

### 7.1 Mode A: Autonomous Mode
* Suitable for automated pipelines, APIs, and headless agents.
* Automatically selects tables and columns exceeding dynamic confidence thresholds ($\ge 0.70$).
* Resolves shortest join paths deterministically.
* Serializes the curated context and hands off immediately.

### 7.2 Mode B: Human-in-the-Loop (HITL) Mode
* Powered by **LangGraph `interrupt` / `resume`**.
* The graph pauses at an interrupt checkpoint and returns a structured inspection payload:
  ```json
  {
    "session_id": "sess_827361",
    "query": "Show monthly revenue by branch in California",
    "status": "awaiting_feedback",
    "candidate_database": "sales_db",
    "candidate_tables": [
      {"table": "branches", "confidence": 0.96, "selected": true, "reason": "matches dimension 'branch' and filter 'California'"},
      {"table": "orders", "confidence": 0.91, "selected": true, "reason": "matches metric 'revenue'"},
      {"table": "branch_audits", "confidence": 0.38, "selected": false, "reason": "low relevance score"}
    ],
    "candidate_columns": [
      {"table": "branches", "column": "state", "selected": true, "enum_match": "CA"},
      {"table": "branches", "column": "branch_name", "selected": true},
      {"table": "orders", "column": "total_amount", "selected": true},
      {"table": "orders", "column": "created_at", "selected": true}
    ],
    "suggested_joins": [
      {
        "source": "orders.branch_id",
        "target": "branches.id",
        "selected": true,
        "type": "physical_foreign_key"
      }
    ]
  }
  ```
* **User Feedback Options:**
  * Toggle table/column checkboxes (include/exclude).
  * Add custom missing tables or columns.
  * Confirm or re-route join paths.
* **Resume & Continuous Learning:**
  * The graph resumes with approved schema selections.
  * Approved pairs `(query, approved_tables, approved_columns, approved_joins)` are indexed in the **Exemplar Memory Store**.
  * Future queries with similar embeddings boost the approved tables and join edges.

---

## 8. Output Contract & Token Budgeting Engine

SchemaLink provides two serialization formats to support downstream agents with strict token budgets:

### 8.1 Compact DDL Serialization (Default, High Token Efficiency)
Compresses schema context by 40–60% compared to verbose JSON:
```sql
-- Database: sales_db (PostgreSQL)
-- Query: "Show monthly revenue by branch in California"
-- Business Rules:
-- 1. Filter orders where status = 'COMPLETED'
-- 2. Revenue corresponds to orders.total_amount

CREATE TABLE branches (
  id bigint PRIMARY KEY,
  branch_name varchar(255),
  state varchar(2) -- Values: ['CA', 'NY', 'TX', ...]
  -- 12 other columns omitted
);

CREATE TABLE orders (
  id bigint PRIMARY KEY,
  branch_id bigint, -- FK -> branches.id
  total_amount numeric(12,2),
  status varchar(30),
  created_at timestamp
  -- 28 other columns omitted
);

-- Join Paths:
-- orders.branch_id = branches.id
```

### 8.2 Structured JSON Serialization (`CuratedSchemaContext`)
For programmatic inspection and agent tools:
```json
{
  "database_id": "sales_db",
  "engine_type": "postgresql",
  "query": "Show monthly revenue by branch in California",
  "selected_tables": [
    {
      "table_name": "branches",
      "description": "Company branch locations",
      "columns": [
        {"name": "id", "type": "bigint", "is_primary_key": true},
        {"name": "branch_name", "type": "varchar(255)", "is_primary_key": false},
        {"name": "state", "type": "varchar(2)", "is_primary_key": false, "matched_literal": "CA"}
      ]
    },
    {
      "table_name": "orders",
      "description": "Customer purchase orders",
      "columns": [
        {"name": "id", "type": "bigint", "is_primary_key": true},
        {"name": "branch_id", "type": "bigint", "is_primary_key": false},
        {"name": "total_amount", "type": "numeric(12,2)", "is_primary_key": false},
        {"name": "created_at", "type": "timestamp", "is_primary_key": false}
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
    "Filter orders where status = 'COMPLETED'",
    "Revenue corresponds to orders.total_amount"
  ],
  "provenance": {
    "mode": "autonomous",
    "retrieval_strategy": "bidirectional_hybrid_rrf_rerank",
    "confidence_score": 0.94
  }
}
```

---

## 9. Security, Governance & Injection Defense

1. **Metadata-Only Principle:** SchemaLink connects with strict read-only metadata permissions (`GRANT SELECT ON pg_catalog` / `information_schema`). No operational records are accessed or vectorized.
2. **Metadata Prompt Injection Defense:** All database comments, table names, and user annotations are escaped and sanitized. Descriptions are wrapped in structured data envelopes rather than raw system instructions to prevent prompt injection from malicious DB comments.
3. **Role-Based Access Control (RBAC):** Supports permission tagging (`allowed_roles: ["finance", "admin"]`). Schema retrieval filters out tables that the calling user or agent lacks permission to view.
4. **Credential Isolation:** Database connection strings are stored encrypted in environment variables or key vaults; credentials are never exposed in logs, outputs, or agent payloads.

---

## 10. Agent & LLM Integration Interfaces

### 10.1 Model Context Protocol (MCP) Server (`src/integrations/mcp_server.py`)
Exposes SchemaLink as a plug-and-play MCP tool for Cursor, Claude Desktop, Antigravity, and MCP clients:
* **Tool Name:** `retrieve_schema`
* **Input Schema:**
  * `query` (str): Natural language question.
  * `database_id` (optional str): Target database identifier.
  * `mode` (str, default `"autonomous"`): Retrieval mode (`"autonomous"` or `"hitl"`).
  * `max_tokens` (int, default `2000`): Maximum token budget for schema output.
* **Output:** Curated Compact DDL or Schema JSON.

### 10.2 Agent Framework Tools (`src/integrations/tools.py`)
Pre-packaged wrappers for:
* **LangChain / LangGraph:** `@tool def retrieve_schema_tool(query: str) -> str`
* **LlamaIndex:** `FunctionTool.from_defaults(fn=retrieve_schema)`
* **OpenAI / Anthropic Function Calling:** Ready-to-use JSON Schema definitions.

### 10.3 Native Python SDK (`src/integrations/client.py`)
```python
from schemalink import SchemaLink

engine = SchemaLink(config_path="schemalink.yaml")
schema_context = await engine.retrieve(
    query="Show monthly revenue by branch in California",
    mode="autonomous",
    format="compact_ddl"
)
print(schema_context.to_prompt())
```

### 10.4 REST API Specification
* `POST /api/v1/databases`: Register a database connection.
* `POST /api/v1/databases/{database_id}/index`: Run schema introspection and indexing.
* `POST /api/v1/databases/{database_id}/sync`: Incremental sync detecting schema diffs via SHA-256 content hashes.
* `POST /api/v1/databases/{database_id}/annotations`: Add or update business synonyms, formulas, and virtual foreign keys.
* `POST /api/v1/retrieval/schema`: Run schema retrieval (`autonomous` or `hitl`).
* `POST /api/v1/retrieval/{session_id}/feedback`: Submit human review modifications and resume workflow.

---

## 11. Incremental Synchronization & Versioning

1. **Deterministic Hashing:** Computes SHA-256 content hashes over column names, types, constraints, and business annotations.
2. **Change Detection:** Detects added, modified, or dropped tables and columns without full index re-computation.
3. **Atomic Blue/Green Index Swapping:** Qdrant collections use version aliases (`sales_db_v1` $\rightarrow$ `sales_db_v2`). The active alias is updated atomically upon index verification, ensuring zero-downtime retrieval during syncs.

---

## 12. Evaluation & Benchmarking Suite

SchemaLink incorporates a dedicated evaluation framework (`src/evaluation/`):
* **Schema Recall@K:** Fraction of ground-truth tables and columns successfully retrieved.
* **Schema Precision@K:** Fraction of retrieved tables and columns that are actually required.
* **Join Path Accuracy:** Percentage of queries where the retrieved join paths form a valid, minimal connecting tree.
* **Token Reduction Ratio:** Percentage reduction in schema tokens compared to full database DDL.
* **Retrieval Latency:** Sub-150ms target for complete bidirectional retrieval and graph resolution.
* **Supported Benchmarks:** Compatible with Spider, BIRD, and Snowflake SQL Schema Retrieval Benchmark.

---

## 13. Repository Directory Structure

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
│   ├── catalog/
│   │   ├── introspection.py
│   │   ├── profiler.py
│   │   ├── models.py
│   │   └── change_detector.py
│   ├── registry/
│   │   └── business_logic.py
│   ├── indexing/
│   │   ├── document_builder.py
│   │   ├── hybrid_store.py
│   │   ├── exemplar_store.py
│   │   └── embeddings.py
│   ├── retrieval/
│   │   ├── query_parser.py
│   │   ├── router.py
│   │   ├── bidirectional.py
│   │   ├── reranker.py
│   │   └── rrf.py
│   ├── graph/
│   │   ├── schema_graph.py
│   │   └── path_finder.py
│   ├── context/
│   │   ├── compactor.py
│   │   ├── tokenizer.py
│   │   └── serializers.py
│   ├── workflow/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── graph.py
│   ├── integrations/
│   │   ├── mcp_server.py
│   │   ├── tools.py
│   │   └── client.py
│   ├── evaluation/
│   │   ├── metrics.py
│   │   └── runner.py
│   └── utils/
│       ├── hashing.py
│       └── security.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── pyproject.toml
├── spec.md
└── README.md
```

---

## 14. Implementation Phasing Roadmap

1. **Phase 1: Catalog Introspection, Profiler & Business Registry**
   * SQLAlchemy generic connector + SQLite / PostgreSQL test fixtures.
   * Low-cardinality categorical value profiler.
   * Business Logic Registry for injecting domain metadata, column formulas, and virtual foreign keys.
2. **Phase 2: Hybrid Indexing & Document Builders**
   * Multi-granularity document modeling (Database, Table, Column).
   * FastEmbed embedding generation + Qdrant hybrid storage (dense + BM25).
3. **Phase 3: Bidirectional Retrieval & NetworkX Join Resolver**
   * Table-first and Column-first retrieval merged via RRF.
   * FlashRank 2nd-stage reranker.
   * Shortest-path join discovery with bridge table injection.
4. **Phase 4: Token Budgeting & Compaction Engine**
   * Compact DDL and Structured JSON context serializers.
   * Intelligent column pruning with token constraints.
5. **Phase 5: LangGraph Workflow & HITL Loop**
   * Dual-mode state machine (Autonomous vs. Interrupt/Resume).
   * Feedback recording and Exemplar Memory index.
6. **Phase 6: Integrations, API & Evaluation**
   * MCP Server, LangChain/LlamaIndex tools, Python SDK.
   * FastAPI REST endpoints.
   * Automated benchmark suite (Recall@K, Join Accuracy, Token Reduction).
