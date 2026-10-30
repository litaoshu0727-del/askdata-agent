from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import sqlite3  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_pipeline.objects import PipelineResult, StepExecutionLog  # noqa: E402
from eval.cases import EvalCase  # noqa: E402
from eval.runner import (  # noqa: E402
    case_ndigits,
    extra_columns_match,
    normalize_value,
    parse_hit_columns,
    round_like_sqlite,
    rows_match,
    run_case,
    score_requirements,
)


def case(query: str) -> EvalCase:
    return EvalCase(id="T", query=query, reference_sql="SELECT 1")


class CaseNdigitsTest(unittest.TestCase):
    """比到几位小数，跟着题面走。"""

    def test_reads_arabic_and_chinese_digits(self):
        self.assertEqual(case_ndigits(case("平均转化率（保留 4 位小数）")), 4)
        self.assertEqual(case_ndigits(case("人均下单笔数（保留3位小数）")), 3)
        self.assertEqual(case_ndigits(case("金额合计，保留两位小数")), 2)
        self.assertEqual(case_ndigits(case("平均分钟数（保留 1 位小数）")), 1)

    def test_defaults_to_two(self):
        self.assertEqual(case_ndigits(case("一共有多少笔订单")), 2)

    def test_takes_the_largest_when_mixed(self):
        """宁严勿松：一句里出现两种位数时按多的比。"""
        self.assertEqual(case_ndigits(case("金额保留 2 位小数，占比保留 4 位小数")), 4)


class RoundLikeSqliteTest(unittest.TestCase):
    """参考 SQL 用 SQLite 的 ROUND 取整，判分得按同一套规则来。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def sqlite_round(self, value, ndigits):
        return self.conn.execute("SELECT ROUND(?, ?)", (value, ndigits)).fetchone()[0]

    def test_exact_halves_round_away_from_zero(self):
        """0.125 正好一半：SQLite 得 0.13，Python round 取偶得 0.12。"""
        for value in (0.125, 0.375, -0.125, 2.5, 0.0625):
            with self.subTest(value=value):
                self.assertEqual(
                    float(round_like_sqlite(value, 2)), self.sqlite_round(value, 2)
                )
        self.assertNotEqual(round(0.125, 2), self.sqlite_round(0.125, 2))

    def test_uses_the_true_binary_value(self):
        """2.675 的二进制值是 2.67499…，SQLite 得 2.67，不是十进制字面上的 2.68。"""
        for value in (2.675, 1.005, 0.285):
            with self.subTest(value=value):
                self.assertEqual(
                    float(round_like_sqlite(value, 2)), self.sqlite_round(value, 2)
                )


class NormalizeValueTest(unittest.TestCase):
    def test_unrounded_model_value_matches_rounded_reference(self):
        """题目要 4 位，模型没取整：比到 4 位照样算对。"""
        self.assertEqual(normalize_value(0.123456, 4), normalize_value(0.1235, 4))

    def test_more_digits_catch_more_errors(self):
        """原先一律比 2 位：0.1234 和 0.1199 都是 0.12，第 3、4 位算错照样判对。"""
        self.assertEqual(normalize_value(0.1234), normalize_value(0.1199))
        self.assertNotEqual(normalize_value(0.1234, 4), normalize_value(0.1199, 4))

    def test_numeric_strings_and_ints(self):
        self.assertEqual(normalize_value("53"), normalize_value(53.0))
        self.assertEqual(normalize_value(53), "53.00")

    def test_negative_zero(self):
        """-0.001 取 2 位是 -0.00，要和 0.00 判成一样。"""
        self.assertEqual(normalize_value(-0.001), normalize_value(0))

    def test_large_numbers_keep_their_digits(self):
        self.assertEqual(normalize_value(1e30), "1000000000000000019884624838656.00")

    def test_text_that_parses_as_float_stays_text(self):
        """float("Nan") 能解析，但叫 Nan 的名字不是数字。"""
        self.assertEqual(normalize_value("Nan"), "Nan")
        self.assertEqual(normalize_value(" Infinity "), "Infinity")

    def test_none_bool_and_plain_text(self):
        self.assertEqual(normalize_value(None), "∅")
        self.assertEqual(normalize_value(True), "True")
        self.assertEqual(normalize_value("  北京 "), "北京")


class RowsMatchTest(unittest.TestCase):
    def test_column_names_and_order_do_not_matter(self):
        actual = [{"total_gmv": 10.0, "city": "北京"}]
        expected = [{"city": "北京", "SUM(gmv)": 10}]
        self.assertTrue(rows_match(actual, expected, False))

    def test_values_cannot_swap_columns_row_by_row(self):
        """员工和上级的名字逐行对调：原先每行各自排序再比，这样也判对。"""
        expected = [{"emp": "张三", "boss": "李四"}, {"emp": "王五", "boss": "赵六"}]
        swapped = [{"emp": "张三", "boss": "李四"}, {"emp": "赵六", "boss": "王五"}]
        self.assertFalse(rows_match(swapped, expected, False))
        # 整列对调是列顺序不同，照样算对
        reordered = [{"b": "李四", "e": "张三"}, {"b": "赵六", "e": "王五"}]
        self.assertTrue(rows_match(reordered, expected, False))

    def test_columns_with_equal_value_sets_are_checked_as_a_whole_table(self):
        """两列各自的值集合都对得上，拼成行却不对：要整表核对，不能只看单列。"""
        expected = [{"a": 1, "b": 2}, {"a": 2, "b": 1}]
        self.assertTrue(rows_match([{"x": 2, "y": 1}, {"x": 1, "y": 2}], expected, False))
        self.assertFalse(rows_match([{"x": 1, "y": 1}, {"x": 2, "y": 2}], expected, False))

    def test_row_order_matters_only_when_ordered(self):
        a = [{"v": 1}, {"v": 2}]
        b = [{"v": 2}, {"v": 1}]
        self.assertTrue(rows_match(a, b, False))
        self.assertFalse(rows_match(a, b, True))

    def test_wrong_values_row_counts_and_widths_are_caught(self):
        expected = [{"v": 1}, {"v": 2}]
        self.assertFalse(rows_match([{"v": 1}], expected, False))
        self.assertFalse(rows_match([{"v": 1}, {"v": 3}], expected, False))
        self.assertFalse(rows_match([{"v": 1, "w": 0}, {"v": 2, "w": 0}], expected, False))
        self.assertTrue(rows_match([], [], False))

    def test_precision_is_passed_through(self):
        a, b = [{"rate": 0.1234}], [{"rate": 0.1199}]
        self.assertTrue(rows_match(a, b, False))
        self.assertFalse(rows_match(a, b, False, 4))


class _FixedAnswerPipeline:
    """不调模型，直接交一个固定答案的链路。"""

    def __init__(self, rows):
        self.rows = rows

    def run(self, query):
        return PipelineResult(
            query=query, keywords=[], schema_context="", cot_output="",
            step_logs=[StepExecutionLog(
                database="db", cot_step=None, local_schema="", sql="SELECT ...",
                execution_request={}, execution_result={"success": True, "rows": self.rows},
            )],
        )


class RunCasePrecisionTest(unittest.TestCase):
    """run_case 要按题面的位数判：参考答案 0.1234，模型交 0.1199。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "empty.db"
        sqlite3.connect(str(self.db)).close()

    def tearDown(self):
        self._tmp.cleanup()

    def judge(self, query, rows):
        item = EvalCase(id="T", query=query, reference_sql="SELECT 0.1234 AS rate")
        return run_case(_FixedAnswerPipeline(rows), self.db, item).status

    def test_four_digits_requested(self):
        self.assertEqual(self.judge("转化率是多少（保留 4 位小数）", [{"rate": 0.1199}]), "wrong_result")
        self.assertEqual(self.judge("转化率是多少（保留 4 位小数）", [{"rate": 0.12341}]), "pass")

    def test_default_two_digits(self):
        self.assertEqual(self.judge("转化率是多少", [{"rate": 0.1199}]), "pass")


class ExtraColumnsTest(unittest.TestCase):
    """
    多返回的列不算错：期望的列都在、行数一样、挑出同一组列能逐行对上。

    H7E17 问"差几单"，模型把两段各自的订单数也一起返回，差值 9 次全对，原先全判错。
    """

    EXPECTED = [{"channel": "APP", "diff": -8}, {"channel": "PC官网", "diff": 20}]

    def test_extra_columns_with_matching_values(self):
        actual = [
            {"channel": "APP", "前段": 76, "后段": 68, "差值": -8},
            {"channel": "PC官网", "前段": 52, "后段": 72, "差值": 20},
        ]
        self.assertEqual(extra_columns_match(actual, self.EXPECTED, False), 2)

    def test_wrong_values_still_fail(self):
        actual = [{"channel": "APP", "前段": 76, "差值": -7}, {"channel": "PC官网", "前段": 52, "差值": 20}]
        self.assertEqual(extra_columns_match(actual, self.EXPECTED, False), -1)

    def test_row_count_must_match(self):
        actual = [{"channel": "APP", "x": 1, "diff": -8}]
        self.assertEqual(extra_columns_match(actual, self.EXPECTED, False), -1)

    def test_columns_are_chosen_once_for_all_rows(self):
        """每行各凑各的不行：第一行的 -8 在 a 列，第二行的 20 在 b 列，没有一组列能同时对上。"""
        actual = [{"channel": "APP", "a": -8, "b": 0}, {"channel": "PC官网", "a": 0, "b": 20}]
        self.assertEqual(extra_columns_match(actual, self.EXPECTED, False), -1)

    def test_same_or_fewer_columns_are_not_widened(self):
        self.assertEqual(extra_columns_match([{"channel": "APP", "diff": -7}, {"channel": "PC官网", "diff": 20}], self.EXPECTED, False), -1)
        self.assertEqual(extra_columns_match([{"diff": -8}, {"diff": 20}], self.EXPECTED, False), -1)

    def test_order_is_respected_when_ordered(self):
        actual = [
            {"channel": "PC官网", "x": 0, "diff": 20},
            {"channel": "APP", "x": 0, "diff": -8},
        ]
        self.assertEqual(extra_columns_match(actual, self.EXPECTED, False), 1)
        self.assertEqual(extra_columns_match(actual, self.EXPECTED, True), -1)

    def test_run_case_passes_and_marks_extra_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "empty.db"
            sqlite3.connect(str(db)).close()
            item = EvalCase(id="T", query="差几单", reference_sql="SELECT 'APP' AS channel, -8 AS diff")
            outcome = run_case(_FixedAnswerPipeline([{"channel": "APP", "前段": 76, "后段": 68, "diff": -8}]), db, item)
            exact = run_case(_FixedAnswerPipeline([{"channel": "APP", "diff": -8}]), db, item)
        self.assertEqual((outcome.status, outcome.extra_columns), ("pass", 2))
        self.assertIn("多返回了 2 列", outcome.detail)
        self.assertEqual((exact.status, exact.extra_columns), ("pass", 0))


class RecallScoringTest(unittest.TestCase):
    CONTEXT = "\n".join([
        "表名：fact_order",
        "- 字段名：order_status",
        "- 字段名：pay_time",
        "表名：dim_user",
        "- 字段名：city",
    ])

    def test_parse_hit_columns(self):
        self.assertEqual(
            parse_hit_columns(self.CONTEXT),
            {"fact_order.order_status", "fact_order.pay_time", "dim_user.city"},
        )

    def test_candidate_groups_need_any_one(self):
        """「某天的订单量」数 fact_order 或 dws_shop_daily 都对，命中任意一个就算。"""
        hits = parse_hit_columns(self.CONTEXT)
        matched, missed = score_requirements(
            ["dim_user.city", ["fact_payment.pay_time", "fact_order.pay_time"], "dim_shop.city"],
            hits,
        )
        self.assertEqual(matched, {"dim_user.city", "fact_order.pay_time"})
        self.assertEqual(missed, ["dim_shop.city"])


if __name__ == "__main__":
    unittest.main()
