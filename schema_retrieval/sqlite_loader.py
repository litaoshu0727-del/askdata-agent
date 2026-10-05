from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from askdata_diagnostics import Codes, emit

from .objects import ColumnSchema, TableRelation, TableSchema


class SQLiteSchemaLoader:
    """SQLite Schema 加载器，用于提取表、字段、主外键和字段样例。"""

    def __init__(
        self,
        db_path: str | Path,
        database_name: str = "main",
        business_meta: Dict[str, Any] | None = None,
        sample_size: int = 5,
    ):
        self.db_path = str(db_path)
        self.database_name = database_name
        self.business_meta = business_meta or {}  # 业务元信息补充，如表描述、字段描述、别名
        self.sample_size = sample_size  # 每个字段最多抽取的样例数量

    def load(self) -> Tuple[Dict[str, TableSchema], List[ColumnSchema], List[TableRelation]]:
        """加载数据库 Schema，返回表信息、字段信息和表关系。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            table_names = self._get_table_names(conn)

            tables: Dict[str, TableSchema] = {}
            columns: List[ColumnSchema] = []
            relations: List[TableRelation] = []

            for table_name in table_names:
                table_meta = self.business_meta.get(table_name, {})

                table_info = conn.execute(
                    f'PRAGMA table_info("{table_name}")'
                ).fetchall()

                foreign_keys = conn.execute(
                    f'PRAGMA foreign_key_list("{table_name}")'
                ).fetchall()

                primary_keys = [
                    row["name"]
                    for row in table_info
                    if row["pk"] and int(row["pk"]) > 0
                ]

                tables[table_name] = TableSchema(
                    database=self.database_name,
                    table_name=table_name,
                    description=table_meta.get("description", ""),
                    aliases=table_meta.get("aliases", []),
                    primary_keys=primary_keys,
                )

                fk_map: Dict[str, str] = {}

                for fk in foreign_keys:
                    source_col = fk["from"]
                    target_table = fk["table"]
                    target_col = fk["to"]

                    fk_map[source_col] = f"{target_table}.{target_col}"

                    relations.append(
                        TableRelation(
                            database=self.database_name,
                            source_table=table_name,
                            source_column=source_col,
                            target_table=target_table,
                            target_column=target_col,
                        )
                    )

                for row in table_info:
                    col_name = row["name"]
                    col_meta = table_meta.get("columns", {}).get(col_name, {})
                    samples = self._get_column_samples(conn, table_name, col_name)

                    columns.append(
                        ColumnSchema(
                            database=self.database_name,
                            table_name=table_name,
                            column_name=col_name,
                            data_type=row["type"] or "UNKNOWN",
                            nullable=not bool(row["notnull"]),
                            description=col_meta.get("description", ""),
                            aliases=col_meta.get("aliases", []),
                            table_description=table_meta.get("description", ""),
                            table_aliases=table_meta.get("aliases", []),
                            samples=samples,
                            time_coverage=self._get_time_coverage(
                                conn, table_name, col_name, row["type"] or "", samples
                            ),
                            is_primary_key=col_name in primary_keys,
                            foreign_key_ref=fk_map.get(col_name),
                        )
                    )

            return tables, columns, relations

        finally:
            conn.close()

    def _get_table_names(self, conn: sqlite3.Connection) -> List[str]:
        """获取业务表名，过滤 SQLite 系统表。"""
        rows = conn.execute(
            '''
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            '''
        ).fetchall()

        return [row["name"] for row in rows]

    # 取值形如 2024-05-01 或 2024-05-01 08:03:00，视为日期/时间
    _DATE_VALUE = re.compile(r"^\d{4}-\d{2}-\d{2}")

    def _get_time_coverage(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        data_type: str,
        samples: List[str],
    ) -> str:
        """
        时间字段的取值范围和覆盖年份，从数据里算，存进 time_coverage，只给时间约束保底用。

        形如"2021-01-01 至 2025-12-22，覆盖 2021年、…、2025年"。保底靠它判断
        "问 2024 年时，哪些时间字段的数据覆盖了 2024 年"——Employee.BirthDate
        覆盖 1947–1973 年，问 2024 年时根本不该是候选。

        **不进精排文本和提示词。**最初它写在 value_range 里：诊断题上精排名额内
        从 50 次升到 53 次，可第三套盲写题上，30 道 ecommerce 题的提示词全变了，
        11 道题的上下文被时间字段换掉了别的字段（新题大多提到"2024 年 5 月"，
        ecommerce 的时间字段又全覆盖 2024 年 5 月）；而 50 道新题里没有一道漏过
        时间字段，它没有可帮的地方。不需要时间的题，不该为它付代价。

        判定只看数据，不看元数据：声明类型带 DATE/TIME，或样例值都形如日期。
        """
        looks_like_time = any(word in data_type.upper() for word in ("DATE", "TIME")) or (
            bool(samples) and all(self._DATE_VALUE.match(value) for value in samples)
        )

        if not looks_like_time:
            return ""

        source = f'FROM "{table_name}" WHERE "{column_name}" IS NOT NULL'

        try:
            low, high = conn.execute(
                f'SELECT MIN("{column_name}"), MAX("{column_name}") {source}'
            ).fetchone()
            months = [
                row[0]
                for row in conn.execute(
                    f'SELECT DISTINCT substr("{column_name}", 1, 7) {source} ORDER BY 1'
                )
            ]
        except sqlite3.Error:
            # 和样例值查的是同一个字段，失败时样例值那边已经发过 COLUMN_SAMPLES_FAILED。
            return ""

        if not all(self._DATE_VALUE.match(str(value)) for value in (low, high)):
            return ""

        # 最早、最晚都像日期，中间仍可能混着 2024-5-1 这种写法，格式不对的月份不算
        months = [month for month in months if re.fullmatch(r"\d{4}-\d{2}", str(month))]
        years = list(dict.fromkeys(month[:4] for month in months))
        first, last = months[0], months[-1]
        span = (int(last[:4]) - int(first[:4])) * 12 + int(last[5:7]) - int(first[5:7]) + 1

        # 跨度在一个季度以内写到月：ecommerce 的订单全在 2024 年 5 月，只写"2024年"太粗
        if span <= 3:
            covered = "、".join(f"{month[:4]}年{int(month[5:7])}月" for month in months)
        elif len(years) <= 10:
            covered = "、".join(f"{year}年" for year in years)
        else:
            covered = f"{years[0]}年 至 {years[-1]}年"

        return f"{str(low)[:10]} 至 {str(high)[:10]}，覆盖 {covered}"

    def _get_column_samples(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
    ) -> List[str]:
        """抽取字段非空样例值，用于增强字段语义。"""
        try:
            sql = (
                f'SELECT DISTINCT "{column_name}" AS value '
                f'FROM "{table_name}" '
                f'WHERE "{column_name}" IS NOT NULL '
                f'LIMIT ?'
            )

            rows = conn.execute(sql, (self.sample_size,)).fetchall()
            return [str(row["value"]) for row in rows if row["value"] is not None]

        except Exception as exc:
            # 样例值缺失会让该字段的索引文本少一块语义，召回质量下降，
            # 但不该让整个加载流程挂掉——所以吞掉异常，同时留下痕迹。
            emit(
                Codes.COLUMN_SAMPLES_FAILED,
                "字段样例值抽取失败，该字段索引文本将缺少样例，召回质量可能下降",
                字段=f"{table_name}.{column_name}",
                原因=str(exc)[:60],
            )
            return []