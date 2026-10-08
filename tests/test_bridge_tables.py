from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema_retrieval.graph_builder import build_schema_graph  # noqa: E402
from schema_retrieval.objects import (  # noqa: E402
    ColumnSchema,
    SchemaHit,
    TableRelation,
    TableSchema,
)

# H4C09 的形态：员工 ← 客户 ← 发票 ← 发票明细 → 曲目 → 流派，另有一张和谁都不连的噪声表。
SCHEMA = {
    "employee": ["employee_id", "employee_name"],
    "customer": ["customer_id", "support_rep_id", "customer_name"],
    "invoice": ["invoice_id", "customer_id", "invoice_name"],
    "invoice_line": ["invoice_line_id", "invoice_id", "track_id"],
    "track": ["track_id", "genre_id", "track_name"],
    "genre": ["genre_id", "genre_name"],
    "noise": ["noise_id", "noise_value"],
    "playlist_track": ["playlist_id", "track_id"],
}
RELATIONS = [
    ("customer", "support_rep_id", "employee", "employee_id"),
    ("invoice", "customer_id", "customer", "customer_id"),
    ("invoice_line", "invoice_id", "invoice", "invoice_id"),
    ("invoice_line", "track_id", "track", "track_id"),
    ("track", "genre_id", "genre", "genre_id"),
    ("playlist_track", "track_id", "track", "track_id"),
    ("employee", "employee_id", "employee", "employee_id"),  # 自关联，不算连通
]

TABLES = {name: TableSchema(database="db", table_name=name) for name in SCHEMA}
COLUMNS = [
    ColumnSchema(database="db", table_name=table, column_name=column, data_type="TEXT")
    for table, columns in SCHEMA.items()
    for column in columns
]
RELS = [
    TableRelation(database="db", source_table=a, source_column=b, target_table=c, target_column=d)
    for a, b, c, d in RELATIONS
]


def hit(table, column):
    column_schema = next(c for c in COLUMNS if c.table_name == table and c.column_name == column)
    return SchemaHit(doc_id=f"{table}.{column}", score=1.0, column=column_schema)


# 检索命中了员工、客户、流派——发票和发票明细一个字段都没被问到
HITS = [hit("employee", "employee_name"), hit("customer", "customer_name"), hit("genre", "genre_name"),
        hit("track", "track_name"), hit("noise", "noise_value")]


def graph(anchors, max_bridge_tables=3, relations=RELS):
    return build_schema_graph(
        hits=list(HITS), tables=TABLES, all_columns=COLUMNS, relations=relations,
        anchor_tables=anchors, max_bridge_tables=max_bridge_tables,
    )


def columns_of(g, table):
    return {c.column_name for c in g.columns.get(table, [])}


class BridgeTablesTest(unittest.TestCase):
    def test_bridges_the_join_path_between_anchor_components(self):
        g = graph(["customer", "genre"])
        self.assertEqual(g.bridge_tables, ["invoice", "invoice_line"])
        # 补了桥接表，关联键跟着两端都选中的关系补进来
        self.assertEqual(columns_of(g, "invoice"), {"invoice_id", "customer_id"})
        self.assertEqual(columns_of(g, "invoice_line"), {"invoice_id", "track_id"})
        self.assertIn("customer_id", columns_of(g, "customer"))

    def test_bridge_tables_get_no_label_column(self):
        """桥接表只为连通而来，只带关联键，不补 invoice_name 这种名称列。"""
        self.assertNotIn("invoice_name", columns_of(graph(["customer", "genre"]), "invoice"))

    def test_components_without_anchor_are_left_alone(self):
        """噪声表那块没有任何关键词的第 1 名，不去连它。"""
        g = graph(["customer", "genre"])
        self.assertIn("noise", g.tables)
        self.assertNotIn("noise", g.bridge_tables)

    def test_anchors_in_one_component_bridge_nothing(self):
        self.assertEqual(graph(["customer", "employee"]).bridge_tables, [])
        self.assertEqual(graph(["genre"]).bridge_tables, [])

    def test_off_by_default_and_capped(self):
        self.assertEqual(graph(["customer", "genre"], max_bridge_tables=0).bridge_tables, [])
        # 要补两张，上限一张：不补，而不是补半条路
        self.assertEqual(graph(["customer", "genre"], max_bridge_tables=1).bridge_tables, [])

    def test_cap_counts_bridges_across_all_components(self):
        """要连三块、每块各要一张桥接表、上限一张：连上第一块就停，不累计超上限。"""
        tables = {t: TableSchema(database="db", table_name=t) for t in "abcxy"}
        columns = [ColumnSchema(database="db", table_name=t, column_name=f"{t}_id", data_type="TEXT") for t in "abcxy"]
        relations = [
            TableRelation(database="db", source_table=s, source_column=f"{s}_id", target_table=t, target_column=f"{t}_id")
            for s, t in (("x", "a"), ("x", "b"), ("y", "b"), ("y", "c"))
        ]
        hits = [SchemaHit(doc_id=t, score=1.0, column=next(c for c in columns if c.table_name == t)) for t in "abc"]
        g = build_schema_graph(hits=hits, tables=tables, all_columns=columns, relations=relations,
                               anchor_tables=["a", "b", "c"], max_bridge_tables=1)
        self.assertEqual(g.bridge_tables, ["x"])

    def test_anchor_outside_selected_tables_is_ignored(self):
        """关键词的第 1 名所在的表没进图，就当这个锚点不存在。"""
        self.assertEqual(graph(["customer", "playlist_track"]).bridge_tables, [])

    def test_all_equally_short_paths_are_added(self):
        """两条一样短的路时都补上，让模型按题意选，而不是猜一条。"""
        extra = RELS + [
            TableRelation(database="db", source_table="playlist_track", source_column="playlist_id",
                          target_table="customer", target_column="customer_id"),
        ]
        # customer → track 现在有两条：经 invoice + invoice_line（两张），或经 playlist_track（一张）
        self.assertEqual(graph(["customer", "track"], relations=extra).bridge_tables, ["playlist_track"])
        extra.append(TableRelation(database="db", source_table="invoice", source_column="customer_id",
                                   target_table="track", target_column="track_id"))
        self.assertEqual(graph(["customer", "track"], relations=extra).bridge_tables, ["invoice", "playlist_track"])

    def test_without_anchors_graph_is_unchanged(self):
        """不传锚点时和原来逐字段一致——两个分步 Demo 走的就是这条路。"""
        old = build_schema_graph(hits=list(HITS), tables=TABLES, all_columns=COLUMNS, relations=RELS)
        new = graph(None)
        self.assertEqual(old.to_prompt_context(), new.to_prompt_context())
        self.assertEqual(new.bridge_tables, [])


if __name__ == "__main__":
    unittest.main()
