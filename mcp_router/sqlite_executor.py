from __future__ import annotations

import re
import sqlite3
import time
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

    这里模拟 MCP 路由到数据库 API 后的执行过程。SQL 是模型写的，所以默认只读。

    只读靠的是连接本身，不是看 SQL 开头。原先只检查 SQL 以 SELECT / WITH 开头，
    而 SQLite 支持 WITH … DELETE / UPDATE / INSERT：

        WITH x AS (SELECT 1) DELETE FROM trade_summary
        → 执行成功，10 行全删

    现在只读模式下用 mode=ro 打开库，再加 PRAGMA query_only，SQL 怎么写都改不了数据。
    开头检查还留着，只为给常见的写操作一句看得懂的报错。
    """

    def __init__(
        self,
        database: str,
        db_path: str | Path,
        timeout: int = 30,
        readonly: bool = True,
        max_seconds: float = 30.0,
    ):
        """
        Args:
            timeout: 等数据库锁的秒数（sqlite3.connect 的 timeout），不是查询时长。
            max_seconds: 单条查询最多跑多久，超过就中断。模型偶尔会写出漏了关联条件的
                笛卡尔积，不设上限会一直卡住。
        """
        self.database = database
        self.db_path = str(db_path)
        self.timeout = timeout
        self.readonly = readonly
        self.max_seconds = max_seconds

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

        conn = None

        try:
            conn = self._connect()
            deadline = time.monotonic() + self.max_seconds
            # 每执行 1000 条虚拟机指令检查一次，返回非零就中断查询
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)

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

            return MCPExecutionResult(
                database=request.database,
                sql=sql,
                success=True,
                columns=columns,
                rows=result_rows,
                row_count=len(result_rows),
            )

        except Exception as exc:
            error = str(exc)

            if isinstance(exc, sqlite3.OperationalError) and error == "interrupted":
                error = f"查询超过 {self.max_seconds:g} 秒被中断，检查是否漏了关联条件"

            return MCPExecutionResult(
                database=request.database,
                sql=sql,
                success=False,
                error=error,
            )

        finally:
            if conn is not None:
                conn.close()

    def _connect(self) -> sqlite3.Connection:
        if not self.readonly:
            return sqlite3.connect(self.db_path, timeout=self.timeout)

        # mode=ro：库不存在时直接报错，而不是悄悄建一个空库
        uri = Path(self.db_path).resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=self.timeout)
        conn.execute("PRAGMA query_only = ON")
        return conn

    def _is_readonly_sql(self, sql: str) -> bool:
        """
        SQL 是否以 SELECT / WITH 开头。

        只用来给常见写操作一句看得懂的报错，不是安全边界——WITH … DELETE 能过这一关，
        挡住它的是只读连接，见 _connect。
        """
        normalized = re.sub(r"\s+", " ", sql.strip()).lower()
        return normalized.startswith("select ") or normalized.startswith("with ")
