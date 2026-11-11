# SchemaLink 🔗
### High-Precision Schema RAG & Discovery Engine for Large-Scale Text-to-SQL

**SchemaLink** is an independent, decoupled Schema RAG engine designed to eliminate context-window overflow and hallucinations in Text-to-SQL systems without vectorizing raw database rows.

---

## 🚀 Key Capabilities

- **Zero Row Vectorization:** Only structured schema metadata, column profiles, and business logic are indexed. The operational database remains the sole source of truth for business data.
- **Hierarchical Multi-Database Routing:** Automatically routes natural language questions to the relevant database, preventing cross-database namespace collisions.
- **Bidirectional Hybrid Retrieval:** Combines Table-first and Column-first hybrid searches (Dense vectors + BM25) fused with Reciprocal Rank Fusion (RRF) and 2nd-stage cross-encoder reranking.
- **Categorical & Enum Profiling:** Discovers low-cardinality enum columns ($\le 50$ distinct values) and maps conversational filter values (e.g. "California") to database literals (e.g. `'CA'`).
- **Deterministic Graph Join Resolution:** Uses in-memory NetworkX graphs over physical foreign keys and user-injected virtual joins to identify required bridge tables.
- **Dual Execution Modes:**
  - **Autonomous Mode:** Fully automated confidence-based filtering and instant context assembly.
  - **Human-in-the-Loop (HITL) Mode:** Pauses execution with LangGraph `interrupt`, outputs an inspection payload, and resumes with human adjustments.
- **Continuous Exemplar Learning:** Approved schema selections in HITL mode are indexed to boost future similar queries.
- **Multiple Agent Interfaces:** Model Context Protocol (MCP) server, LangChain / LlamaIndex tools, in-process Python SDK, and FastAPI REST API.

---

## 🛠️ Quickstart

```python
from schemalink import SchemaLink

# 1. Initialize Engine
engine = SchemaLink()

# 2. Register & Index Database
engine.register_database("sales_db", "sqlite:///ecommerce.db")
engine.index_database("sales_db")

# 3. Retrieve Curated Schema Context
context = engine.retrieve_sync(
    query="Show monthly revenue by branch in California",
    database_id="sales_db",
)

# 4. View Compact DDL Output for Downstream Query Agent
print(context.to_prompt(format_type="compact_ddl"))
```

---

## 🧪 Testing

```bash
pytest tests/ -v
```
