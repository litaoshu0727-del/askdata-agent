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
from askdata_pipeline.result_shape import group_topn_overflow, window_filtered_previous  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402
from eval.runner import BANKS, DATASETS  # noqa: E402
from mcp_router.sqlite_executor import unique_column_names  # noqa: E402

CHINOOK_DB = ROOT / "runtime_data" / "chinook.db"
SAKILA_DB = ROOT / "runtime_data" / "sakila.db"


def execute(conn, sql):
    cursor = conn.execute(sql)
    columns = unique_column_names([item[0] for item in cursor.description])
    return columns, [dict(zip(columns, row)) for row in cursor.fetchall()]


class WindowFilteredPreviousTest(unittest.TestCase):
    """H9S07、H8C02：LAG 和按月 / 按年筛选写在同一层，范围内第一期的上一期被筛掉了。"""

    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.executescript("""
            CREATE TABLE sales (month TEXT, store INTEGER, amount REAL);
            INSERT INTO sales VALUES ('2005-05',1,10),('2005-06',1,15),('2005-07',1,12),('2005-08',1,20),
                                     ('2005-05',2,5),('2005-06',2,6),('2005-07',2,9),('2005-08',2,4);
        """)

    def check(self, sql):
        columns, rows = execute(self.conn, sql)
        return window_filtered_previous(sql, columns, rows)

    def test_lag_with_month_filter_at_the_same_level(self):
        hint = self.check("SELECT month, ROUND(total - LAG(total) OVER (ORDER BY month), 2) AS change "
                          "FROM (SELECT month, SUM(amount) AS total FROM sales GROUP BY month) "
                          "WHERE month BETWEEN '2005-06' AND '2005-08' ORDER BY month")
        self.assertIn("change 里有空值", hint)
        self.assertIn("按 month 筛选", hint)

    def test_window_computed_before_the_filter_is_fine(self):
        sql = ("SELECT month, change FROM (SELECT month, total - LAG(total) OVER (ORDER BY month) AS change "
               "FROM (SELECT month, SUM(amount) AS total FROM sales GROUP BY month)) "
               "WHERE month BETWEEN '2005-06' AND '2005-08'")
        self.assertIsNone(self.check(sql))

    def test_filter_on_another_column_is_fine(self):
        """1 号店每月比上月：第一个月本来就没有上一期，空值是对的。"""
        sql = "SELECT month, amount - LAG(amount) OVER (ORDER BY month) AS change FROM sales WHERE store = 1"
        self.assertIsNone(self.check(sql))

    def test_no_window_or_no_null_is_fine(self):
        for sql in (
            "SELECT month, SUM(amount) FROM sales WHERE month >= '2005-06' GROUP BY month",
            "SELECT month, amount - LAG(amount, 1, 0) OVER (ORDER BY month) AS change FROM sales "
            "WHERE store = 1 AND month >= '2005-06'",
        ):
            with self.subTest(sql=sql):
                self.assertIsNone(self.check(sql))


class GroupTopNOverflowTest(unittest.TestCase):
    """H9S02：问每个类型最能挣钱的两部片子，SQL 没在组内截断，每个类型几十行。"""

    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.executescript("""
            CREATE TABLE film (category TEXT, title TEXT, revenue REAL);
            INSERT INTO film VALUES ('Action','A1',9),('Action','A2',8),('Action','A3',7),
                                    ('Comedy','C1',6),('Comedy','C2',5),('Comedy','C3',4);
        """)

    def check(self, query, sql):
        columns, rows = execute(self.conn, sql)
        return group_topn_overflow(query, columns, rows)

    QUERY = "每个影片类型里，最能挣钱的两部片子是哪两部？列出类型、片名和收入。"

    def test_per_group_top_n_not_cut_off(self):
        hint = self.check(self.QUERY, "SELECT category, title, revenue FROM film ORDER BY category, revenue DESC")
        self.assertIn("每组前 2 没截断", hint)
        self.assertIn("同一个 category 出现了 3 行", hint)

    def test_cut_off_correctly_is_fine(self):
        sql = ("SELECT category, title, revenue FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY category "
               "ORDER BY revenue DESC) AS rn FROM film) WHERE rn <= 2")
        self.assertIsNone(self.check(self.QUERY, sql))

    def test_question_shapes(self):
        all_rows = "SELECT category, title, revenue FROM film"
        cases = {
            "每个类型里收入排前 2 的片子": True,
            "每个类型里收入最高的是哪部片子": True,                     # N = 1
            "每个类型收入最高的两部片子，并列的都算": False,
            "每个类型每年收入最高的两部片子": False,                     # 两层分组
            "收入最高的两部片子": False,                                 # 不是每组
            "每个类型的片子收入合计": False,                             # 没有前 N
            "每个类型首映之前 3 天的收入": False,                       # "之前"不是排名
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(bool(self.check(query, all_rows)), expected)


class ReferenceAnswersAreNeverFlaggedTest(unittest.TestCase):
    """全部题库的参考答案都不触发：离线核对 573 道参考答案、7167 次通过的历史运行，两项误报都是 0。"""

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
                    columns, rows = execute(conn, case.reference_sql)
                    self.assertIsNone(window_filtered_previous(case.reference_sql, columns, rows))
                    self.assertIsNone(group_topn_overflow(case.query, columns, rows))
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


class PipelinePostCheckOrderTest(unittest.TestCase):
    """链路：几项结果检查按顺序查，第一项触发就重新生成一次，后面的不再查。"""

    QUERY = "查询总交易笔数大于50000的利率是多少"   # Mock 内置的题，返回 5 行一列

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        with silenced():
            self.pipeline = AskDataText2SQLPipeline(PipelineConfig(db_path=Path(self._tmp.name) / "trade.db"))

    def tearDown(self):
        self._tmp.cleanup()

    def run_with(self, shape=None, grain=None, window=None, topn=None):
        none = mock.Mock(return_value=None)
        patches = {
            "single_value_mismatch": shape or none,
            "finer_grain_mismatch": grain or none,
            "window_filtered_previous": window or none,
            "group_topn_overflow": topn or none,
        }
        with silenced(), mock.patch.multiple("askdata_pipeline.text2sql_pipeline", **patches):
            return self.pipeline.run(self.QUERY)

    def test_topn_fires_last_in_line(self):
        topn = mock.Mock(side_effect=["没截断", None])
        result = self.run_with(topn=topn)
        self.assertEqual([entry["kind"] for entry in result.sql_trace], ["生成", "前N修正"])
        self.assertIn(Codes.RESULT_TOPN_SUSPECT, {item.code for item in result.diagnostics})

    def test_window_fires_and_later_checks_are_skipped(self):
        window = mock.Mock(side_effect=["上一期被筛掉", None])
        topn = mock.Mock(return_value="没截断")
        result = self.run_with(window=window, topn=topn)
        self.assertEqual([entry["kind"] for entry in result.sql_trace], ["生成", "窗口修正"])
        self.assertIn(Codes.RESULT_WINDOW_SUSPECT, {item.code for item in result.diagnostics})
        topn.assert_not_called()

    def test_earlier_check_wins(self):
        grain = mock.Mock(side_effect=["粒度不对", None])
        window = mock.Mock(return_value="上一期被筛掉")
        result = self.run_with(grain=grain, window=window)
        self.assertEqual([entry["kind"] for entry in result.sql_trace], ["生成", "粒度修正"])
        window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
