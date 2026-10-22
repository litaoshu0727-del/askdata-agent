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

from sql_generation.objects import CotStep, LocalSchema, SqlGenerationRequest, TableColumn, TableSchema  # noqa: E402
from sql_generation.prompt_builder import SQLITE_RULES, SqlPromptBuilder  # noqa: E402


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

    def test_both_prompts_share_one_copy_of_the_rules(self):
        """两份提示词原先各抄一份规则，改一处容易忘了另一处；现在共用 SQLITE_RULES。"""
        for name, prompt in self.prompts.items():
            with self.subTest(提示词=name):
                self.assertIn(SQLITE_RULES, prompt)

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

    def test_one_to_many_rule_in_both_prompts(self):
        """
        H4E27：明细件数合计不少于 6 件的订单按状态数笔数，SQL 把两层 GROUP BY 压成一层，
        或者连上明细表之后再 COUNT。探针上还有 COUNT(DISTINCT) 去了重、SUM 没去重的。
        """
        for name, prompt in self.prompts.items():
            with self.subTest(提示词=name):
                self.assertIn("一对多连接", prompt)
                self.assertIn("不要把两层 GROUP BY 压成一层", prompt)
                self.assertIn("COUNT(DISTINCT) 只救得了笔数，救不了 SUM", prompt)

    def test_group_topn_and_window_rules_in_both_prompts(self):
        """
        第六套：每组前 N 被写成整体排序或全局 LIMIT；修好作用域之后，又在 WHERE 里直接用 LAG(...)。
        """
        for name, prompt in self.prompts.items():
            with self.subTest(提示词=name):
                self.assertIn("组内取前 N", prompt)
                self.assertIn("PARTITION BY 分组列", prompt)
                self.assertIn("外层不再 GROUP BY、不再 SUM", prompt)
                self.assertIn("不能在同一层的 WHERE、GROUP BY、HAVING 里用", prompt)

    def test_time_difference_rule_in_both_prompts(self):
        """
        H7E15："下单后超过一个小时才付款"写成 (julianday(付款) - julianday(下单)) * 24 > 1，正好 1 小时的
        订单算成 1.0000000074 小时，三个版本 9 次全错。探针上 5/35 → 35/35。
        """
        for name, prompt in self.prompts.items():
            with self.subTest(提示词=name):
                self.assertIn("strftime('%s', 晚的) - strftime('%s', 早的)", prompt)
                self.assertIn("不要用 julianday 相减再乘 24 或 1440", prompt)

    def test_uniqueness_and_order_attached_rules_in_both_prompts(self):
        """
        第七套：H7E06、H7C14 把"全都是同一个 X"里的 X 也放进 GROUP BY，HAVING COUNT(DISTINCT X) = 1 每组都成立；
        H7E10 把退款直接连到订单明细再 SUM。模板是看着第一、二版的失败加的。
        """
        for name, prompt in self.prompts.items():
            with self.subTest(提示词=name):
                self.assertIn("HAVING COUNT(DISTINCT X) = 1", prompt)
                self.assertIn("X 不要放进 GROUP BY", prompt)
                self.assertIn("外层再按维度数", prompt)
                self.assertIn("去重的是明细那一侧，不是退款表本身", prompt)

    def test_date_rule_in_both_prompts(self):
        """E44：带时分秒的字段写成 BETWEEN '起始日' AND '结束日'，结束日当天的记录全漏。"""
        for name, prompt in self.prompts.items():
            with self.subTest(提示词=name):
                self.assertIn("DATE(字段) BETWEEN", prompt)


class RepairErrorAnalysisTestCase(unittest.TestCase):
    """
    修正提示的「报错分析」。

    第六套 H6E07、H6C03：子查询把 DATE(create_time) 起了别名，外层又写 DATE(create_time)，报
    no such column: create_time。旧的第 3 条说"报这个错说明它确实不在 Schema 中"，模型对着 Schema
    一看字段明明在，就把原 SQL 原样交回：重放 45 次，原样交回 23 次、修好 21 次；加了分析 45/45。
    """

    def setUp(self):
        schema = LocalSchema(tables={
            "fact_order": TableSchema("fact_order", [TableColumn("create_time"), TableColumn("order_amount")]),
        })
        self.request = SqlGenerationRequest(
            cot_step=CotStep(database="db", processing_objects="fact_order.create_time",
                             operation_instruction="按天汇总", output_target="日期"),
            local_schema=schema,
            sql_dialect="SQLite",
        )
        self.builder = SqlPromptBuilder()

    def repair_prompt(self, error):
        return self.builder.build_repair(self.request, failed_sql="SELECT 1", error=error)

    def test_existing_column_is_explained_as_scope(self):
        for error in ("no such column: create_time", "no such column: t.create_time"):
            with self.subTest(报错=error):
                prompt = self.repair_prompt(error)
                self.assertIn("# 报错分析", prompt)
                self.assertIn("这一层查询看不到它", prompt)
                self.assertIn("fact_order", prompt.split("# 报错分析")[1])

    def test_missing_column_keeps_the_plain_rule(self):
        prompt = self.repair_prompt("no such column: category_id")
        self.assertNotIn("# 报错分析", prompt)
        self.assertIn("不在，就改用Schema里真实存在的字段", prompt)

    def test_window_misuse_is_explained(self):
        prompt = self.repair_prompt("misuse of window function LAG()")
        self.assertIn("# 报错分析", prompt)
        self.assertIn("在外层 WHERE 里按这个别名筛选", prompt)

    def test_other_errors_get_no_analysis(self):
        self.assertNotIn("# 报错分析", self.repair_prompt('near "HAVING": syntax error'))
        self.assertNotIn("# 报错分析", self.repair_prompt("no such function: YEAR"))


if __name__ == "__main__":
    unittest.main()
