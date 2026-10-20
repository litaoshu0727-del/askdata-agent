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
from askdata_pipeline.result_shape import single_value_mismatch  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402
from eval.runner import BANKS, DATASETS  # noqa: E402

CHINOOK_DB = ROOT / "runtime_data" / "chinook.db"


class SingleValueMismatchTest(unittest.TestCase):
    """问题只要一个数、结果却有好几行。第六套"两层聚合压成一层"失败的形状。"""

    def test_count_question_with_many_rows(self):
        hint = single_value_mismatch("有多少位用户曾经在同一天里下过不止一单？", ["COUNT(DISTINCT user_id)"], 50)
        self.assertIn("50 行", hint)
        self.assertIn("外层再 COUNT(*)", hint)

    def test_every_as_a_qualifier_still_counts_when_the_result_is_one_column(self):
        """H6C09："每一首曲目都卖过"里的"每"是限定，不是分组；分组的问题至少还有一列分组键。"""
        query = "有多少张专辑，专辑里的每一首曲目都至少卖出去过一次？"
        self.assertIsNotNone(single_value_mismatch(query, ["cnt"], 48))
        self.assertIsNone(single_value_mismatch(query, ["album", "cnt"], 48))

    def test_grouped_questions_are_left_alone(self):
        for query in ("每个城市有多少位用户？", "按会员等级分，各有多少位？", "哪些店铺一共卖了多少钱？"):
            with self.subTest(query=query):
                self.assertIsNone(single_value_mismatch(query, ["group", "cnt"], 10))

    def test_one_row_or_no_count_question(self):
        self.assertIsNone(single_value_mismatch("有多少位用户？", ["cnt"], 1))
        self.assertIsNone(single_value_mismatch("客户分布在哪些国家", ["Country"], 24))
        self.assertIsNone(single_value_mismatch("查询总交易笔数大于50000的利率是多少", ["interest_rate"], 5))
        self.assertIsNone(single_value_mismatch("", ["cnt"], 5))


class NoReferenceAnswerIsFlaggedTest(unittest.TestCase):
    """全部题库的参考答案都不能被判成"形状不对"——判错了就会把对的答案改掉。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.ecommerce_db = create_ecommerce_demo_database(Path(cls._tmp.name) / "ecommerce.db")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def check(self, dataset, db_path):
        conn = sqlite3.connect(str(db_path))
        try:
            pools = [DATASETS[dataset][0]] + [bank.get(dataset) or [] for bank in BANKS.values()]
            for case in (c for pool in pools for c in pool if not c.expect_unanswerable):
                with self.subTest(case=case.id):
                    cursor = conn.execute(case.reference_sql)
                    rows = cursor.fetchall()
                    columns = [item[0] for item in cursor.description]
                    self.assertIsNone(single_value_mismatch(case.query, columns, len(rows)))
        finally:
            conn.close()

    def test_ecommerce_banks(self):
        self.check("ecommerce", self.ecommerce_db)

    @unittest.skipUnless(CHINOOK_DB.is_file(), "没有 runtime_data/chinook.db（不进仓库，CI 上没有）")
    def test_chinook_banks(self):
        self.check("chinook", CHINOOK_DB)


class PipelineShapeRetryTest(unittest.TestCase):
    """链路：形状可疑时带提示重新生成一次；新结果不再可疑就采用，否则保留原结果。"""

    QUERY = "查询总交易笔数大于50000的利率是多少"   # Mock 内置的题，返回 5 行一列

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        with silenced():
            self.pipeline = AskDataText2SQLPipeline(PipelineConfig(db_path=Path(self._tmp.name) / "trade.db"))

    def tearDown(self):
        self._tmp.cleanup()

    def run_with(self, judge):
        with mock.patch("askdata_pipeline.text2sql_pipeline.single_value_mismatch", side_effect=judge), silenced():
            return self.pipeline.run(self.QUERY)

    def test_retry_is_adopted_when_it_fixes_the_shape(self):
        # 原 SQL 返回 5 行 → 判可疑；Mock 修正交回的还是 Demo SQL，这里让第二次执行只返回一行
        router = self.pipeline.mcp_router
        original = router.execute
        calls = []

        def one_row_on_retry(request):
            calls.append(request)
            result = original(request)
            if len(calls) == 2:
                result.rows, result.row_count = result.rows[:1], 1
            return result

        router.execute = one_row_on_retry
        result = self.run_with(lambda query, columns, rows: "形状不对" if rows > 1 else None)
        self.assertEqual([entry["kind"] for entry in result.sql_trace], ["生成", "形状修正"])
        self.assertEqual(result.step_logs[-1].execution_result["row_count"], 1)
        self.assertIn(Codes.RESULT_SHAPE_SUSPECT, {item.code for item in result.diagnostics})

    def test_original_is_kept_when_the_retry_is_still_suspicious(self):
        # 第二次执行返回 3 行：仍然可疑，留下的应该是原来那 5 行
        router = self.pipeline.mcp_router
        original = router.execute
        calls = []

        def three_rows_on_retry(request):
            calls.append(request)
            result = original(request)
            if len(calls) == 2:
                result.rows, result.row_count = result.rows[:3], 3
            return result

        router.execute = three_rows_on_retry
        result = self.run_with(lambda query, columns, rows: "形状不对")
        self.assertEqual([entry["kind"] for entry in result.sql_trace], ["生成", "形状修正"])
        self.assertEqual(result.step_logs[-1].execution_result["row_count"], 5)

    def test_no_retry_when_the_shape_is_fine(self):
        result = self.run_with(lambda query, columns, rows: None)
        self.assertEqual([entry["kind"] for entry in result.sql_trace], ["生成"])
        self.assertNotIn(Codes.RESULT_SHAPE_SUSPECT, {item.code for item in result.diagnostics})


if __name__ == "__main__":
    unittest.main()
