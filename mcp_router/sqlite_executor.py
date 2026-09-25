from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from .objects import MCPExecutionRequest, MCPExecutionResult


def unique_column_names(names: List[str]) -> List[str]:
    """
    给结果集的列名去重：重名的依次加 _2、_3 后缀。

    自关联查询 SELECT e.FirstName, e.LastName, m.FirstName, m.LastName 的列名是
    ['FirstName', 'LastName', 'FirstName', 'LastName']。原先每行用 dict(row)
    转成字典，同名的键互相覆盖——上级的名字整个丢了，用户只能看到半张表：

        tuple(row) : ('Nancy', 'Edwards', 'Andrew', 'Adams')
        dict(row)  : {'FirstName': 'Nancy', 'LastName': 'Edwards'}

    加出来的后缀也可能和真实列名撞上（比如本来就有一列叫 FirstName_2），
    所以一直加到没被用过为止。
    """
    used: set = set()
    unique: List[str] = []

    for name in names:
        candidate, index = name, 1

        while candidate in used:
            index += 1
            candidate = f"{name}_{index}"

        used.add(candidate)
        unique.append(candidate)

    return unique


class SQLiteMCPExecutor:
    """
    SQLite MCP 执行器。

    这里模拟 MCP 路由到数据库 API 后的执行过程。
    为了 Demo 安全，只允许执行 SELECT / WITH 查询。
    """

    def __init__(
        self,
        database: str,
        db_path: str | Path,
        timeout: int = 30,
        readonly: bool = True,
    ):
        self.database = database
        self.db_path = str(db_path)
        self.timeout = timeout
        self.readonly = readonly

    def execute(self, request: MCPExecutionRequest) -> MCPExecutionResult:
        """
        执行 SQL。
        """
        if request.database != self.database:
            return MCPExecutionResult(
                database=request.database,
                sql=request.sql,
                success=False,
                error=f"数据库路由错误：当前执行器只处理 {self.database}",
            )

        sql = request.sql.strip()

        if self.readonly and not self._is_readonly_sql(sql):
            return MCPExecutionResult(
                database=request.database,
                sql=sql,
                success=False,
                error="只允许执行 SELECT / WITH 查询。",
            )

        try:
            conn = sqlite3.connect(self.db_path, timeout=self.timeout)

            cursor = conn.execute(sql)
            # 列名从 description 取：0 行结果也能拿到列名，而且顺序和位置一一对应。
            columns = unique_column_names(
                [item[0] for item in (cursor.description or [])]
            )

            # 按位置填值，不用 dict(row)——同名列会被合并掉，见 unique_column_names。
            result_rows: List[Dict[str, Any]] = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

            conn.close()

            return MCPExecutionResult(
                database=request.database,
                sql=sql,
                success=True,
                columns=columns,
                rows=result_rows,
                row_count=len(result_rows),
            )

        except Exception as exc:
            return MCPExecutionResult(
                database=request.database,
                sql=sql,
                success=False,
                error=str(exc),
            )

    def _is_readonly_sql(self, sql: str) -> bool:
        """
        判断是否为只读 SQL。
        """
        normalized = re.sub(r"\s+", " ", sql.strip()).lower()
        return normalized.startswith("select ") or normalized.startswith("with ")
