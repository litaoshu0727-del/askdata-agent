from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型。必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "ASKDATA_LOCAL_MODELS"):
    os.environ.pop(_key, None)

import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.rejudge_runs import current_match, find_case, legacy_match  # noqa: E402


class RejudgeTest(unittest.TestCase):
    EXPECTED = [{"emp": "张三", "boss": "李四"}, {"emp": "王五", "boss": "赵六"}]

    def test_old_rule_accepted_row_by_row_swaps_and_the_new_one_does_not(self):
        swapped = [{"emp": "张三", "boss": "李四"}, {"emp": "赵六", "boss": "王五"}]
        self.assertTrue(legacy_match(swapped, self.EXPECTED, False, 2))
        self.assertFalse(current_match(swapped, self.EXPECTED, False, 2))

    def test_extra_columns_are_judged_by_both_rules(self):
        actual = [{"x": 0, "emp": "张三", "boss": "李四"}, {"x": 0, "emp": "王五", "boss": "赵六"}]
        self.assertTrue(legacy_match(actual, self.EXPECTED, False, 2))
        self.assertTrue(current_match(actual, self.EXPECTED, False, 2))

    def test_temporary_bank_names_fall_back_to_the_case_id(self):
        """探针实验的记录用 probe-main、probe-b1 这类临时题库名，按题号还能找到题。"""
        self.assertEqual(find_case("chinook", "probe-holdout2", "HB14").id, "HB14")
        self.assertEqual(find_case("ecommerce_big", "holdout", "H25").id, "H25")
        self.assertIsNone(find_case("ecommerce", "main", "NO_SUCH_CASE"))


if __name__ == "__main__":
    unittest.main()
