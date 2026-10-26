from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型，不加载本地大模型。
# 必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import logging  # noqa: E402

logging.getLogger("askdata").disabled = True

import sqlite3  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from askdata_diagnostics import Codes, silenced  # noqa: E402
from askdata_pipeline.ecommerce_data import create_ecommerce_demo_database  # noqa: E402
from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from askdata_pipeline.result_shape import finer_grain_mismatch  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402
from eval.runner import BANKS, DATASETS  # noqa: E402
from mcp_router.sqlite_executor import unique_column_names  # noqa: E402

CHINOOK_DB = ROOT / "runtime_data" / "chinook.db"
SAKILA_DB = ROOT / "runtime_data" / "sakila.db"


def judge(conn, sql):
    """和执行器一样取结果（重名的列改名），再交给检查。"""
    def run(query):
        cursor = conn.execute(query)
        names = unique_column_names([item[0] for item in cursor.description])
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    cursor = conn.execute(sql)
    columns = unique_column_names([item[0] for item in cursor.description])
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return finer_grain_mismatch(sql, columns, rows, run)


class FinerGrainTest(unittest.TestCase):
    """分组比题目要的细：数了组合（形态 A），同一个维度出现好几行（形态 B）。"""

    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.executescript("""
            CREATE TABLE rental (rental_id INTEGER, customer_id INTEGER, day TEXT);
            INSERT INTO rental VALUES (1,1,'d1'),(2,1,'d1'),(3,1,'d2'),(4,1,'d2'),(5,2,'d1'),(6,2,'d1'),(7,3,'d1');
            CREATE TABLE orders (order_id INTEGER, channel TEXT, amount REAL);
            INSERT INTO orders VALUES (1,'APP',10),(2,'APP',20),(3,'PC',30),(4,'PC',5),(5,'小程序',8);
            CREATE TABLE playlist (PlaylistId INTEGER, Name TEXT);
            INSERT INTO playlist VALUES (1,'Music'),(2,'Movies'),(8,'Music');
            CREATE TABLE playlist_track (PlaylistId INTEGER, TrackId INTEGER);
            INSERT INTO playlist_track VALUES (1,1),(1,2),(2,3),(8,4);
        """)

    def check(self, sql):
        return judge(self.conn, sql)

    # ---- 形态 A
    def test_counting_groups_instead_of_customers(self):
        """H9S13：问有几位客户，数成了（客户, 日期）的组合。"""
        hint = self.check("SELECT COUNT(*) FROM (SELECT customer_id FROM rental "
                          "GROUP BY customer_id, day HAVING COUNT(*) >= 2);")
        self.assertIn("COUNT(DISTINCT customer_id)", hint)
        self.assertIn("3 行里只有 2 个", hint)

    def test_counting_distinct_or_unique_rows_is_fine(self):
        for sql in (
            "SELECT COUNT(DISTINCT customer_id) FROM (SELECT customer_id FROM rental GROUP BY customer_id, day HAVING COUNT(*) >= 2)",
            "SELECT COUNT(*) FROM (SELECT customer_id FROM rental GROUP BY customer_id HAVING COUNT(*) >= 2) t",
            "SELECT COUNT(*) FROM (SELECT customer_id, day FROM rental GROUP BY customer_id, day)",   # 两列：数的就是组合
            "SELECT COUNT(*) FROM (SELECT customer_id FROM rental GROUP BY customer_id, day) WHERE customer_id > 1",
        ):
            with self.subTest(sql=sql):
                self.assertIsNone(self.check(sql))

    def test_subquery_that_cannot_run_alone_is_not_judged(self):
        hint = finer_grain_mismatch("SELECT COUNT(*) FROM (SELECT customer_id FROM rental GROUP BY customer_id, day)",
                                    ["COUNT(*)"], [{"COUNT(*)": 5}], lambda sql: (_ for _ in ()).throw(RuntimeError("x")))
        self.assertIsNone(hint)

    # ---- 形态 B
    def test_grouping_by_a_hidden_column_repeats_the_dimension(self):
        """H7E21 一类：问每个渠道，GROUP BY 渠道, 订单号。"""
        hint = self.check("SELECT channel, SUM(amount) FROM orders GROUP BY channel, order_id")
        self.assertIn("同一个 channel 出现了好几行（5 行里只有 3 种）", hint)

    def test_main_query_after_cte_is_checked(self):
        hint = self.check("WITH t AS (SELECT order_id, channel, amount FROM orders) "
                          "SELECT channel, SUM(amount) AS s FROM t GROUP BY channel, order_id ORDER BY s DESC")
        self.assertIsNotNone(hint)

    def test_proper_grouping_is_fine(self):
        for sql in (
            "SELECT channel, SUM(amount) FROM orders GROUP BY channel",
            "SELECT DISTINCT channel, SUM(amount) FROM orders GROUP BY channel, order_id",
            "SELECT channel, order_id, SUM(amount) FROM orders GROUP BY channel, order_id",
            "SELECT channel, amount FROM orders",                                   # 没有分组的明细，重复是正常的
            "SELECT 'GROUP BY x' AS label, channel, SUM(amount) FROM orders GROUP BY channel",
            "SELECT channel, SUM(amount) FROM orders GROUP BY channel UNION ALL SELECT channel, SUM(amount) FROM orders GROUP BY channel",
        ):
            with self.subTest(sql=sql):
                self.assertIsNone(self.check(sql))

    def test_grouping_by_entity_id_and_showing_its_name_is_fine(self):
        """两个歌单都叫 Music：按歌单 ID 分组、输出歌单名，同名两行是两个歌单，不是分组细了。"""
        sql = ("SELECT p.Name, COUNT(*) FROM playlist p JOIN playlist_track pt ON pt.PlaylistId = p.PlaylistId "
               "GROUP BY p.PlaylistId, p.Name")
        self.assertIsNone(self.check(sql))

    def test_duplicate_column_names_are_not_misread(self):
        """SELECT p.Name, g.Name：执行器把第二个改名成 Name_2，不会被当成同一列重复。"""
        sql = ("SELECT a.Name, b.Name, COUNT(*) FROM playlist a JOIN playlist b ON a.PlaylistId <> b.PlaylistId "
               "GROUP BY a.Name, b.Name")
        self.assertIsNone(self.check(sql))


class ReferenceAnswersAreNeverFlaggedTest(unittest.TestCase):
    """全部题库的参考答案都不触发：离线核对 573 道参考答案、6639 次通过的历史运行，误报都是 0。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.ecommerce_db = create_ecommerce_demo_database(Path(cls._tmp.name) / "ecommerce.db")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def check(self, dataset, db_path):
        cases = list(DATASETS[dataset][0]) + [case for banks in BANKS.values() for case in banks.get(dataset) or []]
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            for case in cases:
                if case.expect_unanswerable:
                    continue
                with self.subTest(case=case.id):
                    self.assertIsNone(judge(conn, case.reference_sql))
        finally:
            conn.close()

    def test_ecommerce(self):
        self.check("ecommerce", self.ecommerce_db)

    @unittest.skipUnless(CHINOOK_DB.is_file(), "没有 runtime_data/chinook.db（不进仓库，CI 上没有）")
    def test_chinook(self):
        self.check("chinook", CHINOOK_DB)

    @unittest.skipUnless(SAKILA_DB.is_file(), "没有 runtime_data/sakila.db（不进仓库，CI 上没有）")
    def test_sakila(self):
        self.check("sakila", SAKILA_DB)


class PipelineGrainRetryTest(unittest.TestCase):
    """链路：粒度可疑时带提示重新生成一次；新结果不再可疑就采用，否则保留原结果；形状检查改过的不再查。"""

    QUERY = "查询总交易笔数大于50000的利率是多少"   # Mock 内置的题，返回 5 行一列

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        with silenced():
            self.pipeline = AskDataText2SQLPipeline(PipelineConfig(db_path=Path(self._tmp.name) / "trade.db"))

    def tearDown(self):
        self._tmp.cleanup()

    def run_with(self, grain, shape=lambda query, columns, rows: None):
        with mock.patch("askdata_pipeline.text2sql_pipeline.finer_grain_mismatch", side_effect=grain), \
                mock.patch("askdata_pipeline.text2sql_pipeline.single_value_mismatch", side_effect=shape), silenced():
            return self.pipeline.run(self.QUERY)

    def rows_on_retry(self, count):
        router = self.pipeline.mcp_router
        original = router.execute
        calls = []

        def execute(request):
            calls.append(request)
            result = original(request)
            if len(calls) == 2:
                result.rows, result.row_count = result.rows[:count], count
            return result

        router.execute = execute

    def test_retry_is_adopted_when_it_fixes_the_grain(self):
        self.rows_on_retry(1)
        result = self.run_with(lambda sql, columns, rows, run: "粒度不对" if len(rows) > 1 else None)
        self.assertEqual([entry["kind"] for entry in result.sql_trace], ["生成", "粒度修正"])
        self.assertEqual(result.step_logs[-1].execution_result["row_count"], 1)
        self.assertIn(Codes.RESULT_GRAIN_SUSPECT, {item.code for item in result.diagnostics})

    def test_original_is_kept_when_the_retry_is_still_suspicious(self):
        self.rows_on_retry(3)
        result = self.run_with(lambda sql, columns, rows, run: "粒度不对")
        self.assertEqual([entry["kind"] for entry in result.sql_trace], ["生成", "粒度修正"])
        self.assertEqual(result.step_logs[-1].execution_result["row_count"], 5)

    def test_no_retry_when_the_grain_is_fine(self):
        result = self.run_with(lambda sql, columns, rows, run: None)
        self.assertEqual([entry["kind"] for entry in result.sql_trace], ["生成"])
        self.assertNotIn(Codes.RESULT_GRAIN_SUSPECT, {item.code for item in result.diagnostics})

    def test_not_checked_after_the_shape_check_fired(self):
        grain = mock.Mock(return_value="粒度不对")
        self.run_with(grain, shape=lambda query, columns, rows: "形状不对")
        grain.assert_not_called()


if __name__ == "__main__":
    unittest.main()
