from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import logging  # noqa: E402

logging.getLogger("askdata").disabled = True

import sqlite3  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.cases import EvalCase  # noqa: E402
from eval.runner import load_expected  # noqa: E402
from mcp_router.objects import MCPExecutionRequest  # noqa: E402
from mcp_router.sqlite_executor import SQLiteMCPExecutor, unique_column_names  # noqa: E402

SELF_JOIN = (
    "SELECT e.FirstName, e.LastName, m.FirstName, m.LastName "
    "FROM Employee e JOIN Employee m ON e.ReportsTo = m.EmployeeId "
    "ORDER BY e.EmployeeId"
)


class SqliteExecutorColumnsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "hr.db"
        conn = sqlite3.connect(str(self.db))
        conn.execute(
            "CREATE TABLE Employee (EmployeeId INTEGER, FirstName TEXT, LastName TEXT, ReportsTo INTEGER)"
        )
        conn.executemany(
            "INSERT INTO Employee VALUES (?, ?, ?, ?)",
            [
                (1, "Andrew", "Adams", None),
                (2, "Nancy", "Edwards", 1),
                (3, "Jane", "Peacock", 2),
            ],
        )
        conn.commit()
        conn.close()
        self.executor = SQLiteMCPExecutor(database="hr_db", db_path=self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def run_sql(self, sql):
        return self.executor.execute(MCPExecutionRequest(database="hr_db", sql=sql))

    def test_self_join_keeps_all_four_columns(self):
        """HB14 的形态：两个 FirstName、两个 LastName，上级的名字不能丢。"""
        result = self.run_sql(SELF_JOIN)

        self.assertTrue(result.success)
        self.assertEqual(result.columns, ["FirstName", "LastName", "FirstName_2", "LastName_2"])
        self.assertEqual(
            [tuple(row.values()) for row in result.rows],
            [("Nancy", "Edwards", "Andrew", "Adams"), ("Jane", "Peacock", "Nancy", "Edwards")],
        )

    def test_columns_match_row_keys(self):
        result = self.run_sql(SELF_JOIN)
        self.assertEqual(list(result.rows[0].keys()), result.columns)

    def test_query_without_duplicates_is_unchanged(self):
        """没有同名列的查询，结果和原先 dict(row) 的写法逐字相同。"""
        result = self.run_sql("SELECT EmployeeId, FirstName FROM Employee ORDER BY EmployeeId")
        self.assertEqual(result.columns, ["EmployeeId", "FirstName"])
        self.assertEqual(
            result.rows,
            [
                {"EmployeeId": 1, "FirstName": "Andrew"},
                {"EmployeeId": 2, "FirstName": "Nancy"},
                {"EmployeeId": 3, "FirstName": "Jane"},
            ],
        )

    def test_empty_result_still_reports_columns(self):
        result = self.run_sql("SELECT FirstName, LastName FROM Employee WHERE 0")
        self.assertTrue(result.success)
        self.assertEqual(result.rows, [])
        self.assertEqual(result.columns, ["FirstName", "LastName"])

    def test_reference_answers_keep_duplicate_columns_too(self):
        """裁判那一侧：参考答案同样不能因为同名列少几列。"""
        case = EvalCase(id="T01", query="", reference_sql=SELF_JOIN)
        expected = load_expected(self.db, case)
        self.assertEqual(
            [tuple(row.values()) for row in expected],
            [("Nancy", "Edwards", "Andrew", "Adams"), ("Jane", "Peacock", "Nancy", "Edwards")],
        )


class SqliteExecutorReadonlyTest(unittest.TestCase):
    """
    只读靠连接，不靠看 SQL 开头。

    原先只检查 SQL 以 SELECT / WITH 开头，WITH x AS (SELECT 1) DELETE FROM … 能过，
    在 trade 库的副本上实测把 10 行全删了。
    """

    WRITES = [
        "WITH x AS (SELECT 1) DELETE FROM t",
        "WITH x AS (SELECT 1) UPDATE t SET v = 0",
        "WITH x AS (SELECT 9) INSERT INTO t SELECT * FROM x",
        "DELETE FROM t",
        "DROP TABLE t",
    ]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "库 with space.db"   # 路径里有中文和空格，URI 要编码对
        conn = sqlite3.connect(str(self.db))
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(10)])
        conn.commit()
        conn.close()

    def tearDown(self):
        self._tmp.cleanup()

    def run_sql(self, sql, **kwargs):
        executor = SQLiteMCPExecutor(database="db", db_path=self.db, **kwargs)
        return executor.execute(MCPExecutionRequest(database="db", sql=sql))

    def table_rows(self):
        conn = sqlite3.connect(str(self.db))
        try:
            return conn.execute("SELECT COUNT(*), SUM(v) FROM t").fetchone()
        finally:
            conn.close()

    def test_writes_are_rejected_and_data_unchanged(self):
        for sql in self.WRITES:
            with self.subTest(sql=sql):
                self.assertFalse(self.run_sql(sql).success)
                self.assertEqual(self.table_rows(), (10, 45))

    def test_with_select_still_works(self):
        result = self.run_sql("WITH x AS (SELECT v FROM t WHERE v > 7) SELECT COUNT(*) AS n FROM x")
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.rows, [{"n": 2}])

    def test_missing_database_is_not_created(self):
        """mode=ro 下库不存在要报错，不能悄悄建一个空库再返回 0 行。"""
        missing = Path(self._tmp.name) / "missing.db"
        executor = SQLiteMCPExecutor(database="db", db_path=missing)
        result = executor.execute(MCPExecutionRequest(database="db", sql="SELECT 1"))
        self.assertFalse(result.success)
        self.assertFalse(missing.exists())

    def test_runaway_query_is_interrupted(self):
        """
        漏了关联条件的笛卡尔积，超时就中断，不能一直卡住。

        用有限的慢查询（2000 万行，不中断约 1 秒），不用无限递归：中断失效时测试
        应该很快失败，而不是把整个测试套件挂住。
        """
        result = self.run_sql(
            "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 20000000) "
            "SELECT COUNT(*) FROM n",
            max_seconds=0.05,
        )
        self.assertFalse(result.success)
        self.assertIn("中断", result.error)

    def test_readonly_false_can_write(self):
        """
        显式关掉只读时写操作能执行——确认上面的拒绝来自只读，而不是别的错误。

        WITH 开头的写不受 Python sqlite3 隐式事务管，执行完就落盘；原先那个漏洞
        之所以真能删掉数据，靠的正是这一点。
        """
        result = self.run_sql("WITH x AS (SELECT 0) DELETE FROM t WHERE v IN x", readonly=False)
        self.assertTrue(result.success, result.error)
        self.assertEqual(self.table_rows(), (9, 45))


class UniqueColumnNamesTest(unittest.TestCase):
    def test_duplicates_get_suffixes(self):
        self.assertEqual(
            unique_column_names(["a", "b", "a", "a"]),
            ["a", "b", "a_2", "a_3"],
        )

    def test_suffix_never_collides_with_a_real_column(self):
        """本来就有一列叫 a_2 时，生成的名字要绕开它。"""
        self.assertEqual(
            unique_column_names(["a", "a_2", "a"]),
            ["a", "a_2", "a_3"],
        )
        names = unique_column_names(["x", "x", "x_2"])
        self.assertEqual(len(names), len(set(names)))

    def test_no_duplicates_passes_through(self):
        self.assertEqual(unique_column_names(["id", "name"]), ["id", "name"])


if __name__ == "__main__":
    unittest.main()
