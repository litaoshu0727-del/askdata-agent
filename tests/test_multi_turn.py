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

# 降级告警在测试里是预期行为，不需要刷到 stderr；断言仍然基于 collect() 的结果。
import logging  # noqa: E402

logging.getLogger("askdata").disabled = True

import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from askdata_diagnostics import Codes, collect, silenced  # noqa: E402
from askdata_pipeline.data_qa import build_metric_glossary  # noqa: E402
from askdata_pipeline.ecommerce_data import get_ecommerce_business_meta  # noqa: E402
from askdata_pipeline.query_rewriter import (  # noqa: E402
    ContextualQueryRewriter,
    QueryRewriterConfig,
)

CONTEXT = '[近期对话] 用户：销售额最高的三个店铺是哪些 助手：查询结果：臻品自营店15、优选旗舰店1、旗舰旗舰店7'


class ReferenceDetectionTestCase(unittest.TestCase):
    """指代词检测：决定要不要多花一次模型调用。"""

    def test_detects_common_reference_words(self):
        for query in [
            "它们的退款金额分别是多少",
            "这些店铺的买家数",
            "刚才第一名叫什么",
            "上述店铺的转化率",
            "其中哪家最高",
        ]:
            with self.subTest(问题=query):
                self.assertTrue(ContextualQueryRewriter.looks_contextual(query))

    def test_self_contained_query_needs_no_rewrite(self):
        for query in [
            "销售额最高的三个店铺是哪些",
            "客单价最高的10个用户是谁",
            "因为商品质量问题退款的总金额是多少",
        ]:
            with self.subTest(问题=query):
                self.assertFalse(ContextualQueryRewriter.looks_contextual(query))


class RewriteSkipTestCase(unittest.TestCase):
    """不该调模型的几种情况，必须短路返回。"""

    def setUp(self):
        self.rewriter = ContextualQueryRewriter(QueryRewriterConfig(api_key=""))

    def test_no_context_skips(self):
        result = self.rewriter.rewrite("它们的退款金额呢", "")

        self.assertFalse(result.changed)
        self.assertEqual(result.effective, "它们的退款金额呢")
        self.assertEqual(result.skipped_reason, "无会话上下文")

    def test_no_reference_word_skips_without_calling_model(self):
        """自包含的问题不该浪费一次模型调用。"""
        result = self.rewriter.rewrite("销售额最高的三个店铺是哪些", CONTEXT)

        self.assertFalse(result.changed)
        self.assertEqual(result.skipped_reason, "未检测到指代词")

    def test_missing_api_key_emits_diagnostic(self):
        """
        有指代词却没有 Key，是"多轮追问必定不正确"的状态，
        不能安静地退化成按字面查询。
        """
        with silenced(), collect() as diagnostics:
            result = self.rewriter.rewrite("它们的退款金额呢", CONTEXT)

        self.assertFalse(result.changed)
        self.assertEqual(result.effective, "它们的退款金额呢")
        self.assertIn(
            Codes.QUERY_REWRITE_SKIPPED,
            {item.code for item in diagnostics},
        )


class RewriteWithStubModelTestCase(unittest.TestCase):
    """接一个假模型，验证改写结果被正确清洗和传递。"""

    def _rewriter(self, reply: str) -> ContextualQueryRewriter:
        rewriter = ContextualQueryRewriter(
            QueryRewriterConfig(
                api_key="sk-stub",
                chat_url="https://example.invalid/chat",
                model="stub",
            )
        )
        rewriter._call_model = lambda prompt: reply
        return rewriter

    def test_rewrite_replaces_reference(self):
        rewriter = self._rewriter("臻品自营店15、优选旗舰店1、旗舰旗舰店7的退款金额分别是多少")
        result = rewriter.rewrite("它们的退款金额分别是多少", CONTEXT)

        self.assertTrue(result.changed)
        self.assertIn("臻品自营店15", result.effective)
        self.assertNotIn("它们", result.effective)

    def test_quotes_are_stripped(self):
        rewriter = self._rewriter('"臻品自营店15的退款金额是多少"')
        result = rewriter.rewrite("它的退款金额是多少", CONTEXT)

        self.assertFalse(result.effective.startswith('"'))

    def test_model_failure_falls_back_to_original(self):
        rewriter = ContextualQueryRewriter(
            QueryRewriterConfig(api_key="sk-stub", chat_url="x", model="stub")
        )

        def boom(prompt):
            raise RuntimeError("网络炸了")

        rewriter._call_model = boom

        with silenced(), collect() as diagnostics:
            result = rewriter.rewrite("它们的退款金额呢", CONTEXT)

        self.assertEqual(result.effective, "它们的退款金额呢")
        self.assertIn(
            Codes.QUERY_REWRITE_FAILED,
            {item.code for item in diagnostics},
        )


class MetricGlossaryTestCase(unittest.TestCase):
    """
    指标口径表。

    "客单价怎么算的"曾经答不出来，因为 data_qa 只拿得到会话记忆、看不到 Schema。
    """

    def setUp(self):
        self.glossary = build_metric_glossary(get_ecommerce_business_meta())

    def test_glossary_maps_business_term_to_column(self):
        self.assertIn("客单价", self.glossary)
        self.assertIn("dws_user_summary.avg_order_amount", self.glossary)

    def test_glossary_covers_ambiguous_amount_fields(self):
        for fragment in [
            "dws_shop_daily.gmv",
            "fact_order.pay_amount",
            "fact_refund.refund_amount",
        ]:
            with self.subTest(字段=fragment):
                self.assertIn(fragment, self.glossary)

    def test_empty_meta_returns_empty_glossary(self):
        self.assertEqual(build_metric_glossary(None), "")
        self.assertEqual(build_metric_glossary({}), "")

    def test_glossary_is_truncated(self):
        glossary = build_metric_glossary(get_ecommerce_business_meta(), max_chars=200)

        self.assertLessEqual(len(glossary), 260)
        self.assertIn("已截断", glossary)


if __name__ == "__main__":
    unittest.main()
