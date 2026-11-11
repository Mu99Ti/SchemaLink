"""In-memory NetworkX relationship graph and bridge path resolver."""

from __future__ import annotations

import logging

import networkx as nx

from src.catalog.models import DatabaseInfo
from src.models.context import JoinPath
from src.registry.business_logic import BusinessLogicRegistry

logger = logging.getLogger(__name__)


class SchemaRelationshipGraph:
    """Maintains a directed multigraph of table foreign keys and virtual relationships."""

    def __init__(self, database_id: str):
        self.database_id = database_id
        self.graph = nx.MultiDiGraph()

    def build_from_catalog(
        self,
        db_info: DatabaseInfo,
        registry: BusinessLogicRegistry | None = None,
    ) -> None:
        self.graph.clear()

        # Add table nodes
        for table in db_info.tables:
            self.graph.add_node(
                table.table_name,
                schema=table.schema_name,
                columns=[c.name for c in table.columns],
                primary_keys=table.primary_key_columns,
            )

        # 1. Add physical foreign keys (weight: 1.0)
        for table in db_info.tables:
            for fk in table.foreign_keys:
                self.graph.add_edge(
                    table.table_name,
                    fk.target_table,
                    key=f"{table.table_name}.{fk.source_column}->{fk.target_table}.{fk.target_column}",
                    source_column=fk.source_column,
                    target_column=fk.target_column,
                    relationship_type="physical_foreign_key",
                    weight=1.0,
                    confidence=1.0,
                )
                # Add reverse edge for undirected path search
                self.graph.add_edge(
                    fk.target_table,
                    table.table_name,
                    key=f"{fk.target_table}.{fk.target_column}<-{table.table_name}.{fk.source_column}",
                    source_column=fk.target_column,
                    target_column=fk.source_column,
                    relationship_type="physical_foreign_key_reverse",
                    weight=1.0,
                    confidence=1.0,
                )

        # 2. Add user-injected virtual foreign keys (weight: 1.05)
        if registry:
            ann = registry.get_database_annotation(self.database_id)
            for vfk in ann.virtual_foreign_keys:
                self.graph.add_edge(
                    vfk.source_table,
                    vfk.target_table,
                    key=f"v:{vfk.source_table}.{vfk.source_column}->{vfk.target_table}.{vfk.target_column}",
                    source_column=vfk.source_column,
                    target_column=vfk.target_column,
                    relationship_type=vfk.relationship_type,
                    weight=1.05,
                    confidence=vfk.confidence,
                )
                self.graph.add_edge(
                    vfk.target_table,
                    vfk.source_table,
                    key=f"v:{vfk.target_table}.{vfk.target_column}<-{vfk.source_table}.{vfk.source_column}",
                    source_column=vfk.target_column,
                    target_column=vfk.source_column,
                    relationship_type=f"{vfk.relationship_type}_reverse",
                    weight=1.05,
                    confidence=vfk.confidence,
                )

    def find_connecting_subgraph(self, target_tables: list[str]) -> tuple[list[str], list[JoinPath]]:
        """Given a list of candidate tables, finds intermediate bridge tables and returns all join paths."""
        valid_targets = [t for t in target_tables if self.graph.has_node(t)]
        if len(valid_targets) <= 1:
            return valid_targets, []

        all_needed_tables = set(valid_targets)
        discovered_joins: list[JoinPath] = []
        seen_join_signatures = set()

        # Undirected view for shortest path connectivity
        undirected_g = self.graph.to_undirected(as_view=False)

        # Pairwise shortest paths between all target tables
        for i in range(len(valid_targets)):
            for j in range(i + 1, len(valid_targets)):
                u, v = valid_targets[i], valid_targets[j]
                if nx.has_path(undirected_g, u, v):
                    try:
                        path_nodes = nx.shortest_path(undirected_g, u, v, weight="weight")
                        # Add any intermediate bridge tables
                        for node in path_nodes:
                            all_needed_tables.add(node)

                        # Extract edges along path
                        for k in range(len(path_nodes) - 1):
                            n1, n2 = path_nodes[k], path_nodes[k + 1]
                            edge_data = self.graph.get_edge_data(n1, n2)
                            if edge_data:
                                # Pick edge with best confidence
                                best_edge = sorted(edge_data.values(), key=lambda e: e.get("confidence", 0), reverse=True)[0]
                                sig = f"{n1}.{best_edge['source_column']}={n2}.{best_edge['target_column']}"
                                rev_sig = f"{n2}.{best_edge['target_column']}={n1}.{best_edge['source_column']}"
                                if sig not in seen_join_signatures and rev_sig not in seen_join_signatures:
                                    seen_join_signatures.add(sig)
                                    discovered_joins.append(
                                        JoinPath(
                                            source_table=n1,
                                            source_column=best_edge["source_column"],
                                            target_table=n2,
                                            target_column=best_edge["target_column"],
                                            relationship_type=best_edge.get("relationship_type", "foreign_key"),
                                            confidence=best_edge.get("confidence", 1.0),
                                        )
                                    )
                    except nx.NetworkXNoPath:
                        continue

        return list(all_needed_tables), discovered_joins
