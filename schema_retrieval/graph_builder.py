from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set

from .objects import ColumnSchema, SchemaGraph, SchemaHit, TableRelation, TableSchema


def build_schema_graph(
    hits: List[SchemaHit],
    tables: Dict[str, TableSchema],
    all_columns: List[ColumnSchema],
    relations: List[TableRelation],
    include_join_columns: bool = True,
    include_label_columns: bool = True,
    anchor_tables: Optional[Iterable[str]] = None,
    max_bridge_tables: int = 0,
) -> SchemaGraph:
    """
    根据检索命中的字段构建 Schema 子图。

    输入：
    - hits: 检索命中的字段。
    - tables: 全量表 Schema。
    - all_columns: 全量字段 Schema。
    - relations: 全量表关系。
    - anchor_tables: 问题里各个检索意图落在哪些表上（每个关键词自己排第 1 的字段所在的表）。
      这些表之间不连通时，沿外键补桥接表，见 _bridge_tables。
    - max_bridge_tables: 最多补几张桥接表，0 表示不补。

    输出：
    - 仅包含相关表、相关字段、相关关联关系的 SchemaGraph。
    """

    selected_tables = {hit.column.table_name for hit in hits}

    selected_columns = defaultdict(dict)

    for hit in hits:
        col = hit.column
        selected_columns[col.table_name][col.column_name] = col

    # 沿命中的外键做一跳扩展：把外键指向的维表拉进来。
    #
    # 「单笔实付金额最高的订单是哪个用户下的」，检索命中了 fact_order.user_id，
    # 但 dim_user 整张表都没进图——因为关系要求两端都已命中才会被选中。
    # 结果模型手上只有 user_id，只能输出一串数字。
    #
    # 只扩展"有名称列"的表，也就是维表。事实表之间不做扩展，避免图膨胀。
    if include_label_columns:
        for hit in list(hits):
            reference = getattr(hit.column, "foreign_key_ref", "") or ""

            if "." not in reference:
                continue

            referenced_table = reference.split(".", 1)[0]

            if referenced_table in selected_tables:
                continue

            if _find_label_column(all_columns, referenced_table) is None:
                continue

            selected_tables.add(referenced_table)

    bridge_tables = _bridge_tables(selected_tables, anchor_tables or [], relations, max_bridge_tables)
    selected_tables |= bridge_tables

    selected_relations: List[TableRelation] = []

    for relation in relations:
        source_selected = relation.source_table in selected_tables
        target_selected = relation.target_table in selected_tables

        if source_selected and target_selected:
            selected_relations.append(relation)

            if include_join_columns:
                source_col = _find_column(
                    all_columns,
                    relation.source_table,
                    relation.source_column,
                )
                target_col = _find_column(
                    all_columns,
                    relation.target_table,
                    relation.target_column,
                )

                if source_col:
                    selected_columns[relation.source_table][relation.source_column] = source_col

                if target_col:
                    selected_columns[relation.target_table][relation.target_column] = target_col

    # 凡是被选中的表，把它的"名称列"一并带上。
    #
    # 检索天然偏向指标字段：用户问"销售额最高的店铺是哪家"，
    # "销售额"是显式的检索词，"店铺名称"却是隐含需求——Query 里
    # 根本没有"名称"两个字。结果就是 gmv 召回了、shop_name 没召回，
    # 模型只能输出 shop_id，答非所问。
    #
    # 这和 include_join_columns 是同一类补偿：关联键也不会出现在
    # 用户的问法里，但没有它就没法 JOIN。名称列同理——没有它就没法作答。
    # 桥接表不补名称列：它们只为连通而来，只要关联键。
    if include_label_columns:
        for table_name in selected_tables - bridge_tables:
            label_column = _find_label_column(all_columns, table_name)

            if label_column and label_column.column_name not in selected_columns[table_name]:
                selected_columns[table_name][label_column.column_name] = label_column

    graph_tables = {
        table_name: tables[table_name]
        for table_name in selected_tables
        if table_name in tables
    }

    graph_columns = {
        table_name: list(column_map.values())
        for table_name, column_map in selected_columns.items()
    }

    database = ""
    if graph_tables:
        database = next(iter(graph_tables.values())).database

    return SchemaGraph(
        database=database,
        tables=graph_tables,
        columns=graph_columns,
        relations=selected_relations,
        bridge_tables=sorted(bridge_tables),
    )


def _bridge_tables(
    selected_tables: Set[str],
    anchor_tables: Iterable[str],
    relations: List[TableRelation],
    max_bridge_tables: int,
) -> Set[str]:
    """
    问题要跨的几块表之间不连通时，沿外键找最短路径，返回路径上要补的桥接表。

    关联键原本只在一条关系两端的表都被选中时才补。可问题要走的连接路径上，常有一张
    桥接表自己一个字段都没被问到：

        H4C09「每位销售支持员工负责的客户中，买过 Jazz 流派曲目的客户各有几位」
        选中 Customer、Employee、Genre、Track，图分成 {Customer, Employee} 和
        {Genre, Track} 两块——中间的 Invoice、InvoiceLine 没人提，关联键也就补不上。
        CoT 判缺失，每次都靠全量 Schema 复核救回；库大到全量放不进提示词时就是错答案。

    不能见到不连通就连：主题库和留出集 245 次运行里 102 次的图不连通，绝大多数多出来的
    那块是检索带进来的无关表，连上只会多塞几张表。所以只连"锚点"所在的块——每个关键词
    自己排第 1 的字段所在的表。一块里没有任何关键词的第 1 名，就当它是噪声。

    最短路径不止一条时全补上：挑一条可能挑错连接路径（比如用户和商品之间，经浏览行为
    还是经购买明细），都给出来让模型按题意选。超过 max_bridge_tables 张就不补。
    """
    if max_bridge_tables <= 0:
        return set()

    adjacency: Dict[str, Set[str]] = defaultdict(set)
    for relation in relations:
        if relation.source_table == relation.target_table:
            continue
        adjacency[relation.source_table].add(relation.target_table)
        adjacency[relation.target_table].add(relation.source_table)

    def component(start: str, tables: Set[str]) -> Set[str]:
        seen, stack = set(), [start]
        while stack:
            table = stack.pop()
            if table in seen:
                continue
            seen.add(table)
            stack.extend(n for n in adjacency[table] if n in tables)
        return seen

    anchor_components: List[Set[str]] = []
    for anchor in sorted(set(anchor_tables)):
        if anchor not in selected_tables:
            continue
        piece = component(anchor, selected_tables)
        if piece not in anchor_components:
            anchor_components.append(piece)

    if len(anchor_components) < 2:
        return set()

    connected = set(anchor_components[0])
    bridges: Set[str] = set()

    for piece in anchor_components[1:]:
        if piece & connected:
            continue

        paths = _shortest_paths(connected, piece, adjacency, max_bridge_tables)
        middle = {table for path in paths for table in path}

        if not paths or len(bridges | middle) > max_bridge_tables:
            continue

        bridges |= middle
        connected |= middle | piece

    return bridges


def _shortest_paths(
    sources: Set[str],
    targets: Set[str],
    adjacency: Dict[str, Set[str]],
    max_middle: int,
) -> List[List[str]]:
    """从 sources 到 targets 的所有最短路径，只返回中间的表；中间超过 max_middle 张就不找了。"""
    frontier = [[table] for table in sorted(sources)]

    for _ in range(max_middle + 1):
        found, next_frontier = [], []

        for path in frontier:
            for neighbor in sorted(adjacency[path[-1]]):
                if neighbor in path or neighbor in sources:
                    continue
                if neighbor in targets:
                    found.append(path[1:])
                else:
                    next_frontier.append(path + [neighbor])

        if found:
            return found

        frontier = next_frontier

    return []


def _find_label_column(
    columns: List[ColumnSchema],
    table_name: str,
) -> ColumnSchema | None:
    """
    找出一张表的"名称列"，也就是用来指代这条记录的那一列。

    两级判定：
    1. 业务元数据里显式标注 semantic_role="output_dimension" 的列；
    2. 没标注时退回命名约定，优先 <表名去掉前缀>_name，其次任意 *_name。

    显式优先、约定兜底——换一个库不写元数据也能work，
    写了元数据则以元数据为准。
    """
    candidates = [column for column in columns if column.table_name == table_name]

    if not candidates:
        return None

    for column in candidates:
        if getattr(column, "semantic_role", "") == "output_dimension":
            return column

    # dim_shop -> shop_name，dim_user -> user_name
    entity = table_name.split("_", 1)[-1] if "_" in table_name else table_name
    preferred = f"{entity}_name"

    for column in candidates:
        if column.column_name == preferred:
            return column

    for column in candidates:
        if column.column_name.endswith("_name"):
            return column

    return None


def _find_column(
    columns: List[ColumnSchema],
    table_name: str,
    column_name: str,
) -> ColumnSchema | None:
    for column in columns:
        if column.table_name == table_name and column.column_name == column_name:
            return column

    return None
