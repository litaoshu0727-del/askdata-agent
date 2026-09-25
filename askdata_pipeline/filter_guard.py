"""
筛选值守卫：问题里提到的取值，SQL 有没有用上。

这是为一种最危险的失败形态准备的——**零告警的错答案**。

    E19「用户浏览行为的平均停留时长」
        behavior_type 没召回 → CoT 看不到这个字段，也不觉得缺什么
        → 生成 SELECT AVG(stay_seconds) FROM fact_user_behavior，直接去掉了筛选
        → 300.47（参考 296.02），降级记录一条都没有

    E51「上海的店铺卖给北京用户的已完成订单，实付金额合计」
        order_status 没召回 → 模型拿 finish_time IS NOT NULL 凑"已完成"
        → 59436.98（参考 44149.54），降级记录一条都没有

全量 Schema 复核救不了它们：复核只在 CoT **自己说缺失**时触发，而这两次 CoT
根本没意识到缺了什么。缺的是一个不依赖 CoT 自觉的检查。

裁判用的是数据库本身。「浏览」「已完成」「北京」恰好是某些字段的枚举取值，
库里查得到。问题提到了某个取值，而 SQL 里既没有这个取值、也没碰它所属的字段，
那这个筛选条件就是被丢了。整个检查是确定性的，不调 LLM。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Set

TEXT_TYPE_MARKERS = ("CHAR", "TEXT", "CLOB")


@dataclass
class DroppedFilter:
    """问题里提到、SQL 却没用上的一个取值。"""

    value: str
    columns: List[str] = field(default_factory=list)
    """这个取值出现在哪些字段里，形如 table.column。"""

    def render(self) -> str:
        return f"「{self.value}」（{' / '.join(self.columns)}）"


class FilterValueGuard:
    """
    枚举取值索引 + 丢失检查。

    只收低基数的文本字段：订单状态、渠道、城市、类目名这类。高基数字段
    （商品名、用户名、时间戳）一来太大，二来问题里提到它们多半是在问而不是在筛。
    """

    def __init__(self, value_columns: Dict[str, Set[str]]):
        self.value_columns = value_columns

        # 长的先匹配："数码电器"命中了就不再拿"数码"去算一次
        self._ordered_values = sorted(value_columns, key=len, reverse=True)

    @classmethod
    def from_sqlite(
        cls,
        db_path: str | Path,
        max_distinct: int = 50,
        min_length: int = 2,
    ) -> "FilterValueGuard":
        """
        扫一遍库，建取值索引。

        Args:
            max_distinct: 去重取值超过这个数的字段不收。
            min_length: 取值短于这个长度的不收——单字取值（男 / 女）
                在中文问句里太容易误撞。
        """
        value_columns: Dict[str, Set[str]] = {}

        conn = sqlite3.connect(str(db_path))

        try:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            ]

            for table in tables:
                for _, column, declared_type, *_ in conn.execute(
                    f'PRAGMA table_info("{table}")'
                ):
                    declared = (declared_type or "").upper()

                    if declared and not any(m in declared for m in TEXT_TYPE_MARKERS):
                        continue

                    rows = conn.execute(
                        f'SELECT DISTINCT "{column}" FROM "{table}" '
                        f'WHERE "{column}" IS NOT NULL LIMIT ?',
                        (max_distinct + 1,),
                    ).fetchall()

                    if len(rows) > max_distinct:
                        continue

                    for (value,) in rows:
                        text = str(value).strip()

                        if len(text) < min_length:
                            continue

                        value_columns.setdefault(text, set()).add(f"{table}.{column}")
        finally:
            conn.close()

        return cls(value_columns)

    def mentioned_values(self, query: str) -> List[str]:
        """
        问题里提到了哪些取值。

        不重叠、长的优先。英文取值要求词边界，免得 "Pop" 撞上 "Population"。
        """
        taken = [False] * len(query)
        found: List[str] = []

        for value in self._ordered_values:
            for match in self._iter_matches(query, value):
                start, end = match.span()

                if any(taken[start:end]):
                    continue

                for index in range(start, end):
                    taken[index] = True

                if value not in found:
                    found.append(value)

        return found

    def find_dropped(self, query: str, sqls: Iterable[str]) -> List[DroppedFilter]:
        """
        问题提到了、SQL 却没用上的取值。

        "没用上"的判据刻意放得很宽：SQL 里出现了这个取值，**或者**出现了它所属
        字段的字段名，都算用上了。后者是为了容忍换一种写法的筛选——比如
        order_status IN (...) 或 order_status <> '待支付'。只抓整个条件都不见了的情况。
        """
        sql_text = "\n".join(sqls)
        dropped: List[DroppedFilter] = []

        for value in self.mentioned_values(query):
            if value in sql_text:
                continue

            columns = sorted(self.value_columns[value])
            column_names = {column.split(".", 1)[1] for column in columns}

            if any(re.search(rf"\b{re.escape(name)}\b", sql_text) for name in column_names):
                continue

            dropped.append(DroppedFilter(value=value, columns=columns))

        return dropped

    @staticmethod
    def _iter_matches(query: str, value: str):
        if value.isascii():
            return re.finditer(rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])", query)

        return re.finditer(re.escape(value), query)
