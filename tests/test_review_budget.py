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

import logging  # noqa: E402

logging.getLogger("askdata").disabled = True

import sys  # noqa: E402
import tempfile  # noqa: E402
from types import SimpleNamespace  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_diagnostics import Codes, collect, silenced  # noqa: E402
from askdata_pipeline.filter_guard import DroppedFilter  # noqa: E402
from askdata_pipeline.objects import PipelineConfig  # noqa: E402
from askdata_pipeline.text2sql_pipeline import AskDataText2SQLPipeline  # noqa: E402


def size(graph):
    return len(graph.to_prompt_context())


class ReviewSchemaBudgetTest(unittest.TestCase):
    """全量 Schema 放不下时，复核逐级收：外键一跳 → 只要选中表 → 不复核。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        with silenced():
            cls.pipeline = AskDataText2SQLPipeline(PipelineConfig(
                dataset="ecommerce", database_name="ecommerce_db",
                db_path=Path(cls._tmp.name) / "ecommerce.db",
            ))
        p = cls.pipeline
        cls.base = p._schema_graph_for_tables({"fact_refund"})
        cls.full_size = size(p._build_full_schema_graph())
        # fact_refund 外键指向 fact_order，一跳只多一张表
        cls.one_hop = p._schema_graph_for_tables({"fact_refund", "fact_order"})
        cls.one_hop_size, cls.selected_size = size(cls.one_hop), size(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def review(self, budget, extra_tables=()):
        self.pipeline.config.review_schema_char_budget = budget
        with collect() as diagnostics:
            graph = self.pipeline._review_schema_graph(self.base, extra_tables=extra_tables)
        return graph, [d.code for d in diagnostics]

    def test_sizes_are_ordered_as_the_test_assumes(self):
        self.assertLess(self.selected_size, self.one_hop_size)
        self.assertLess(self.one_hop_size, self.full_size)

    def test_within_budget_uses_full_schema(self):
        """当前三个库都远在预算内：行为和原来一样，给全量，不留记录。"""
        for budget in (0, self.full_size, 40000):
            with self.subTest(budget=budget):
                graph, codes = self.review(budget)
                self.assertEqual(len(graph.tables), 11)
                self.assertNotIn(Codes.REVIEW_SCHEMA_BOUNDED, codes)

    def test_over_budget_uses_selected_tables_plus_one_hop(self):
        graph, codes = self.review(self.one_hop_size)
        self.assertEqual(set(graph.tables), {"fact_refund", "fact_order"})
        # 选中表的全部字段都在，不只是检索命中的那几个
        refund_columns = {c.column_name for c in graph.columns["fact_refund"]}
        self.assertTrue({"refund_amount", "refund_reason", "refund_status", "finish_time"} <= refund_columns)
        self.assertEqual(codes, [Codes.REVIEW_SCHEMA_BOUNDED])

    def test_falls_back_to_selected_tables_only(self):
        graph, codes = self.review(self.one_hop_size - 1)
        self.assertEqual(set(graph.tables), {"fact_refund"})
        self.assertEqual(codes, [Codes.REVIEW_SCHEMA_BOUNDED])

    def test_nothing_fits_means_no_review(self):
        graph, codes = self.review(self.selected_size - 1)
        self.assertIsNone(graph)
        self.assertEqual(codes, [Codes.REVIEW_SCHEMA_BOUNDED])

    def test_extra_tables_are_included(self):
        """守卫重规划时，被丢取值所属的表一定要在里面。"""
        graph, _ = self.review(self.full_size - 1, extra_tables={"fact_user_behavior"})
        self.assertIn("fact_user_behavior", graph.tables)

    def test_relations_only_between_included_tables(self):
        graph, _ = self.review(self.one_hop_size)
        for relation in graph.relations:
            self.assertIn(relation.source_table, graph.tables)
            self.assertIn(relation.target_table, graph.tables)


class _DropOnce:
    def __init__(self):
        self.calls = 0

    def find_dropped(self, query, sqls):
        self.calls += 1
        return [DroppedFilter(value="已支付", columns=["fact_order.order_status"])] if self.calls == 1 else []


class BudgetAtCallSitesTest(unittest.TestCase):
    """两个调用点：放不下时拒答复核不再多调一次 CoT，守卫不重规划但照样留记录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        with silenced():
            self.pipeline = AskDataText2SQLPipeline(PipelineConfig(db_path=Path(self._tmp.name) / "trade.db"))
        self.pipeline.config.review_schema_char_budget = 1  # 什么都放不下

    def tearDown(self):
        self._tmp.cleanup()

    def test_refusal_is_not_reviewed_when_nothing_fits(self):
        calls = []
        missing = SimpleNamespace(database="缺失", processing_objects="缺少员工数据",
                                  operation_instruction="", output_target="缺失")

        def refusing(**kwargs):
            calls.append(kwargs["schema_graph"])
            return SimpleNamespace(steps=[missing], raw_output="数据库: 缺失")

        self.pipeline.cot_planner.plan = refusing
        with silenced():
            result = self.pipeline.run("每家店铺有多少名员工")

        # run() 内部自己收集降级记录，放在 result.diagnostics 里
        codes = [d.code for d in result.diagnostics]
        self.assertEqual(len(calls), 1)
        self.assertIn(Codes.REVIEW_SCHEMA_BOUNDED, codes)
        self.assertNotIn(Codes.SCHEMA_RECALL_MISS, codes)
        self.assertIn(Codes.SCHEMA_INSUFFICIENT, codes)  # 拒答照常生效

    def test_refusal_is_reviewed_with_full_schema_when_it_fits(self):
        """对照：放得下时照旧复核——CoT 被调两次，第二次看的是全量。"""
        self.pipeline.config.review_schema_char_budget = 40000
        calls = []
        missing = SimpleNamespace(database="缺失", processing_objects="缺少员工数据",
                                  operation_instruction="", output_target="缺失")

        def refusing(**kwargs):
            calls.append(kwargs["schema_graph"])
            return SimpleNamespace(steps=[missing], raw_output="数据库: 缺失")

        self.pipeline.cot_planner.plan = refusing
        with silenced():
            self.pipeline.run("每家店铺有多少名员工")

        self.assertEqual(len(calls), 2)
        self.assertEqual(set(calls[1].tables), set(self.pipeline.schema_retrieval_service.tables))

    def test_guard_does_not_replan_when_nothing_fits(self):
        self.pipeline.filter_guard = _DropOnce()
        with silenced():
            result = self.pipeline.run("查询总交易笔数大于50000的利率是多少")

        self.assertEqual([entry["phase"] for entry in result.sql_trace], ["首轮"])
        dropped = [d for d in result.diagnostics if d.code == Codes.FILTER_VALUE_DROPPED]
        self.assertEqual(len(dropped), 1)
        self.assertIn("没有重规划", dropped[0].render())


    def test_guard_passes_the_dropped_values_tables(self):
        """守卫重规划要求的 Schema 里，必须带上被丢取值所属的表。"""
        self.pipeline.filter_guard = _DropOnce()
        seen = []
        original = self.pipeline._review_schema_graph

        def spy(base_graph, extra_tables=()):
            seen.append(set(extra_tables))
            return original(base_graph, extra_tables=extra_tables)

        self.pipeline._review_schema_graph = spy
        with silenced():
            self.pipeline.run("查询总交易笔数大于50000的利率是多少")

        self.assertIn({"fact_order"}, seen)

if __name__ == "__main__":
    unittest.main()
