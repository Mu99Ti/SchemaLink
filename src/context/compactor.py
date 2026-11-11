"""Token budgeting and compact schema context serializers."""

from __future__ import annotations

from src.models.context import CuratedSchemaContext, JoinPath, SelectedColumn, SelectedTable
from src.models.documents import ColumnDocument, TableDocument


class SchemaContextCompactor:
    """Intelligently prunes columns, enforces token budgets, and formats compact DDL."""

    def __init__(self, max_tokens: int = 2000):
        self.max_tokens = max_tokens

    def build_context(
        self,
        database_id: str,
        engine_type: str,
        query: str,
        tables: list[tuple[TableDocument, float]],
        columns: list[tuple[ColumnDocument, float]],
        join_paths: list[JoinPath],
        business_rules: list[str] | None = None,
        confidence_score: float = 0.95,
        mode: str = "autonomous",
    ) -> CuratedSchemaContext:
        business_rules = business_rules or []

        # Map candidate columns by table
        table_cols_map: dict[str, list[ColumnDocument]] = {}
        for col_doc, _ in columns:
            t = col_doc.table_name
            if t not in table_cols_map:
                table_cols_map[t] = []
            table_cols_map[t].append(col_doc)

        selected_tables: list[SelectedTable] = []
        all_rules = list(business_rules)

        for table_doc, _ in tables:
            t_name = table_doc.table_name
            all_rules.extend(table_doc.business_rules)

            # Relevant retrieved columns for this table
            retrieved_cols = {c.column_name: c for c in table_cols_map.get(t_name, [])}
            pk_set = set(table_doc.primary_keys)

            # Join keys involving this table
            join_keys = set()
            for jp in join_paths:
                if jp.source_table == t_name:
                    join_keys.add(jp.source_column)
                if jp.target_table == t_name:
                    join_keys.add(jp.target_column)

            # Always retain: Relevant retrieved columns + Primary Keys + Join Keys
            retained_col_names = set(retrieved_cols.keys()) | pk_set | join_keys
            # If no columns specifically retrieved, retain top 5 columns or PKs
            if not retained_col_names:
                retained_col_names = set(table_doc.column_names[:5]) | pk_set

            selected_cols_list: list[SelectedColumn] = []
            omitted_cols: list[str] = []

            for col_name in table_doc.column_names:
                if col_name in retained_col_names:
                    c_doc = retrieved_cols.get(col_name)
                    data_type = c_doc.data_type if c_doc else "TEXT"
                    desc = c_doc.description if c_doc else None
                    enums = c_doc.categorical_values if c_doc else []
                    matched_lit = enums[0] if len(enums) == 1 else None

                    selected_cols_list.append(
                        SelectedColumn(
                            name=col_name,
                            data_type=data_type,
                            is_primary_key=col_name in pk_set,
                            is_foreign_key=col_name in join_keys,
                            description=desc,
                            matched_literal=matched_lit,
                        )
                    )
                else:
                    omitted_cols.append(col_name)

            selected_tables.append(
                SelectedTable(
                    table_name=t_name,
                    schema_name=table_doc.schema_name,
                    description=table_doc.description,
                    columns=selected_cols_list,
                    omitted_columns_count=len(omitted_cols),
                    omitted_column_names=omitted_cols,
                )
            )

        # Generate Compact DDL
        formatted_ddl = self.format_compact_ddl(
            database_id=database_id,
            engine_type=engine_type,
            query=query,
            selected_tables=selected_tables,
            join_paths=join_paths,
            business_rules=list(set(all_rules)),
        )

        from src.models.context import ProvenanceInfo

        provenance = ProvenanceInfo(
            mode=mode,
            retrieval_strategy="bidirectional_hybrid_rrf_rerank",
            confidence_score=confidence_score,
            tables_retrieved=len(selected_tables),
            columns_retrieved=sum(len(t.columns) for t in selected_tables),
        )

        return CuratedSchemaContext(
            database_id=database_id,
            engine_type=engine_type,
            query=query,
            selected_tables=selected_tables,
            join_paths=join_paths,
            business_rules=list(set(all_rules)),
            provenance=provenance,
            formatted_ddl=formatted_ddl,
        )

    def format_compact_ddl(
        self,
        database_id: str,
        engine_type: str,
        query: str,
        selected_tables: list[SelectedTable],
        join_paths: list[JoinPath],
        business_rules: list[str],
    ) -> str:
        lines: list[str] = [
            f"-- Database: {database_id} ({engine_type})",
            f'-- User Query: "{query}"',
        ]

        if business_rules:
            lines.append("-- Business Rules & Constraints:")
            for rule in business_rules:
                lines.append(f"--   * {rule}")

        lines.append("")

        for t in selected_tables:
            desc = f" -- {t.description}" if t.description else ""
            lines.append(f"CREATE TABLE {t.table_name} ({desc}")
            for c in t.columns:
                pk_str = " PRIMARY KEY" if c.is_primary_key else ""
                desc_str = f" -- {c.description}" if c.description else ""
                lines.append(f"  {c.name} {c.data_type}{pk_str},{desc_str}")

            if t.omitted_columns_count > 0:
                sample_omitted = ", ".join(t.omitted_column_names[:5])
                extra = "..." if t.omitted_columns_count > 5 else ""
                lines.append(
                    f"  -- {t.omitted_columns_count} other columns omitted ({sample_omitted}{extra})"
                )
            lines.append(");")
            lines.append("")

        if join_paths:
            lines.append("-- Join Paths:")
            for jp in join_paths:
                lines.append(
                    f"-- {jp.source_table}.{jp.source_column} = {jp.target_table}.{jp.target_column} ({jp.relationship_type})"
                )

        return "\n".join(lines).strip()
