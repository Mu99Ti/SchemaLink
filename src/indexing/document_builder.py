"""Multi-granularity document builder for database schemas."""

from __future__ import annotations

from src.catalog.models import ColumnProfile, DatabaseInfo
from src.models.documents import ColumnDocument, DatabaseDocument, TableDocument
from src.registry.business_logic import BusinessLogicRegistry
from src.utils.hashing import content_hash


class SchemaDocumentBuilder:
    """Builds indexable Database, Table, and Column documents from catalog and business annotations."""

    def __init__(self, registry: BusinessLogicRegistry | None = None):
        self.registry = registry or BusinessLogicRegistry()

    def build_documents(
        self,
        db_info: DatabaseInfo,
        profiles: dict[str, ColumnProfile] | None = None,
    ) -> tuple[DatabaseDocument, list[TableDocument], list[ColumnDocument]]:
        profiles = profiles or {}
        ann = self.registry.get_database_annotation(db_info.database_id)

        # 1. Database Document
        db_desc = ann.description or f"Relational database ({db_info.engine_type}) named {db_info.database_name}"
        db_hash = content_hash(db_info.database_id, db_info.engine_type, db_desc, "".join(ann.domains))
        db_doc = DatabaseDocument(
            document_id=f"db_{db_info.database_id}",
            database_id=db_info.database_id,
            engine_type=db_info.engine_type,
            domains=ann.domains or [db_info.database_id],
            description=db_desc,
            content_hash=db_hash,
            metadata={"database_name": db_info.database_name, "tables_count": len(db_info.tables)},
        )

        table_docs: list[TableDocument] = []
        column_docs: list[ColumnDocument] = []

        # 2. Table & Column Documents
        for table in db_info.tables:
            t_ann = ann.tables.get(table.table_name)
            t_desc = (t_ann.description if t_ann and t_ann.description else table.comment) or f"Table containing {table.table_name} records"
            t_terms = t_ann.business_synonyms if t_ann else []
            t_rules = t_ann.business_rules if t_ann else []

            col_names = [c.name for c in table.columns]
            fks = [
                {
                    "source_column": fk.source_column,
                    "target_table": fk.target_table,
                    "target_column": fk.target_column,
                }
                for fk in table.foreign_keys
            ]

            t_hash = content_hash(
                db_info.database_id,
                table.table_name,
                t_desc,
                "".join(t_terms),
                "".join(col_names),
                "".join(t_rules),
            )

            table_doc = TableDocument(
                document_id=f"{db_info.database_id}.{table.schema_name or 'public'}.{table.table_name}",
                database_id=db_info.database_id,
                schema_name=table.schema_name,
                table_name=table.table_name,
                description=t_desc,
                business_terms=t_terms,
                business_rules=t_rules,
                column_names=col_names,
                primary_keys=table.primary_key_columns,
                foreign_keys=fks,
                content_hash=t_hash,
                metadata={"table_type": table.table_type, "column_count": len(col_names)},
            )
            table_docs.append(table_doc)

            # Columns
            for col in table.columns:
                col_key = f"{table.table_name}.{col.name}"
                c_ann = ann.columns.get(col_key)

                c_desc = (c_ann.description if c_ann and c_ann.description else col.comment) or f"Column {col.name} ({col.data_type})"
                if c_ann and c_ann.calculation_formula:
                    c_desc += f". Formula: {c_ann.calculation_formula}"

                c_terms = c_ann.business_synonyms if c_ann else []
                profile = profiles.get(col_key)
                enums = profile.distinct_values if profile else []

                c_hash = content_hash(
                    db_info.database_id,
                    table.table_name,
                    col.name,
                    col.data_type,
                    c_desc,
                    "".join(c_terms),
                    "".join(enums),
                )

                col_doc = ColumnDocument(
                    document_id=f"{db_info.database_id}.{table.schema_name or 'public'}.{table.table_name}.{col.name}",
                    database_id=db_info.database_id,
                    schema_name=table.schema_name,
                    table_name=table.table_name,
                    column_name=col.name,
                    data_type=col.data_type,
                    is_primary_key=col.is_primary_key,
                    is_foreign_key=col.is_foreign_key,
                    description=c_desc,
                    business_terms=c_terms,
                    categorical_values=enums,
                    parent_table_description=t_desc,
                    content_hash=c_hash,
                    metadata={"nullable": col.nullable, "default": col.default},
                )
                column_docs.append(col_doc)

        return db_doc, table_docs, column_docs
