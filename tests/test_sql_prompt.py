from __future__ import annotations

# 单元测试在隔离环境下运行：不读 .env，不调真实模型，不加载本地大模型。
# 必须写在导入项目模块之前。
import os  # noqa: E402

os.environ["ASKDATA_DISABLE_DOTENV"] = "1"
for _key in (
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_WORKSPACE_ID",
    "ASKDATA_LOCAL_MODELS",
):
    os.environ.pop(_key, None)

import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sql_generation.objects import CotStep, LocalSchema, SqlGenerationRequest  # noqa: E402
from sql_generation.prompt_builder import SqlPromptBuilder  # noqa: E402


class SqlPromptRulesTestCase(unittest.TestCase):
    """
    回归守卫：SQL 提示词里的 SQLite 规则。

    规则写在两处——生成提示词和修正提示词。改其中一处时最容易忘了另一处，
    修正那一步缺了规则，修出来的 SQL 会把同一个坑再踩一遍。
    """

    def setUp(self):
        request = SqlGenerationRequest(
            cot_step=CotStep(
                database="db",
                processing_objects="t.a",
                operation_instruction="求平均",
                output_target="t.a",
            ),
            local_schema=LocalSchema(),
            sql_dialect="SQLite",
        )
        builder = SqlPromptBuilder()
        self.prompts = {
            "生成": builder.build(request),
            "修正": builder.build_repair(request, failed_sql="SELECT 1", error="no such column: x"),
        }

    def test_integer_division_rule_in_both_prompts(self):
        """H3E14：SUM(下单笔数) / COUNT(用户) 被截断成整数，三个版本 9 次里错了 6 次。"""
        for name, prompt in self.prompts.items():
            with self.subTest(提示词=name):
                self.assertIn("两个整数相除", prompt)
                self.assertIn("乘以 1.0", prompt)

    def test_cross_table_ratio_hint_in_both_prompts(self):
        """
        只加整数除法那一句时，"发票总数 ÷ 客户总数"被写成 COUNT(a) * 1.0 / COUNT(b) FROM A, B，
        两张表一连接，分子分母数的都是连接后的行数，答案成了 1.0。
        """
        for name, prompt in self.prompts.items():
            with self.subTest(提示词=name):
                self.assertIn("各自用子查询算好再相除", prompt)

    def test_date_rule_in_both_prompts(self):
        """E44：带时分秒的字段写成 BETWEEN '起始日' AND '结束日'，结束日当天的记录全漏。"""
        for name, prompt in self.prompts.items():
            with self.subTest(提示词=name):
                self.assertIn("DATE(字段) BETWEEN", prompt)


if __name__ == "__main__":
    unittest.main()
